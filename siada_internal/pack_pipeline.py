import logging
import os
import re
import shutil
from enum import Enum

from client.ois_s3_client import ClientOptions, OisS3Client

siada_version = "unknown"
dist_directory = os.path.abspath(os.environ.get("SIADA_DIST_DIR", "dist/"))
script_directory = "scripts/"
remote_install_file = "remote_install.sh"
test_remote_install_file = "test_remote_install.sh"
remote_install_ps1_file = "remote_install.ps1"
test_remote_install_ps1_file = "test_remote_install.ps1"

REMOTE_INSTALL_TEMPLATE = None


class SiadaOis(Enum):
    PROD = "prod"
    TEST = "test"


def create_functional_client_options():
    return ClientOptions(
        env="prod",
        region="cnhb01",
        app_id="li-mate-script",
        ois_service_url="https://ois3-cnhb01.inner.chj.cloud",
        idaas_client_id="68mciPunejX12UAygzIrTK",
        idaas_client_secret="eyJrdHkiOiJvY3QiLCJraWQiOiJid2lLb0QzVWt3IiwiYWxnIjoiSFMyNTYiLCJrIjoic0hpUnY0ZTNVSDRaMkdoTVEzOEZ0aGJLck1naVNCUkJ5UzZJdVFlWmE5NCJ9",
        idaas_service_id="2sgXStuBk7e22KCV6s6QtY"
    )


def find_largest_whl(directory):
    # Validate directory and list all files
    if not os.path.isdir(directory):
        logging.error(f"Dist directory not found: {directory}")
        return None
    files = os.listdir(directory)

    # Filter files ending with .whl
    whl_files = [f for f in files if f.endswith('.whl')]
    if not whl_files:
        return None

    # Extract version number using regex (support hyphen or underscore between name parts)
    def extract_version(filename):
        match = re.search(r'(?:siada[-_]cli)-(\d+(?:\.\d+)+)', filename)
        if match:
            return tuple(map(int, match.group(1).split('.')))
        return (0, 0, 0)

    # Find the file with the highest version
    max_file = max(whl_files, key=extract_version, default=None)

    return max_file


def copy_and_rename(file_path, new_name, target_directory):
    # Compose the new file path
    new_file_path = os.path.join(target_directory, new_name)

    # Copy and rename the file
    shutil.copy(file_path, new_file_path)


def upload_file_to_ois(file_paths: list, siada_ois_env: str):
    try:
        client_options = create_functional_client_options()
        ois_s3_client = OisS3Client(client_options)
        for file_path in file_paths:
            with open(file_path, 'rb') as file_stream:
                # Upload by passing the file stream
                file_name = os.path.basename(file_path)
                response = ois_s3_client.put_object("siada", f"/cli-install/{siada_ois_env}/{file_name}", file_stream)
                if response.is_succeed():
                    print(f"{file_path} uploaded to OIS successfully!")
                else:
                    print(f"error: code = {response.code}, message = {response.message}")
    except Exception as e:
        logging.error(e)


if __name__ == '__main__':
    siada_ois_env = os.environ.get("SIADA_OIS", SiadaOis.TEST.value)

    if siada_ois_env.lower() == SiadaOis.PROD.value:
        # confirm to user to upload to prod
        confirm = input("Are you sure to upload to prod? (y/n): ")
        if confirm.lower() != "y":
            exit(1)

    prod_upload_files = []
    test_upload_files = []
    # unified list to always include the wheel for upload
    common_upload_files = []
    largest_whl_file = find_largest_whl(dist_directory)

    if largest_whl_file:
        print("Largest version file:", largest_whl_file)
        # Derive siada version from wheel filename
        _m = re.search(r"(?:siada[-_]cli)-(\d+(?:\.\d+)+)", largest_whl_file)
        if _m:
            siada_version = _m.group(1)
        full_whl_path = os.path.join(dist_directory, largest_whl_file)
        if not os.path.isdir(dist_directory):
            print(f"Dist directory not found: {dist_directory}")
            exit(1)
        if not os.path.exists(full_whl_path):
            print(f"Wheel not found: {full_whl_path}")
            exit(1)
        common_upload_files.append(full_whl_path)
        print(f"whl file: {full_whl_path}")
    else:
        print("No matching .whl file found.")
        exit(1)

    # Ensure scripts directory exists and load template content from file for syntax highlighting
    os.makedirs(script_directory, exist_ok=True)
    template_sh_path = os.path.join(script_directory, "template.sh")
    with open(template_sh_path, "r") as tf:
        template_sh_content = tf.read()
    template_ps1_path = os.path.join(script_directory, "template.ps1")
    with open(template_ps1_path, "r") as pf:
        template_ps1_content = pf.read()

    if siada_ois_env.lower() == SiadaOis.PROD.value:
        with open(script_directory + remote_install_file, "w") as f:
            # Avoid parsing shell ${...} syntax by using simple replacements
            remote_script = (
                template_sh_content
                .replace("$env", siada_ois_env)
                .replace("$file_name", largest_whl_file)
            )
            f.write(remote_script)
            prod_upload_files.append(script_directory + remote_install_file)
        # Windows PowerShell script
        with open(script_directory + remote_install_ps1_file, "w") as f:
            remote_script_ps1 = (
                template_ps1_content
                .replace("$env", siada_ois_env)
                .replace("$file_name", largest_whl_file)
            )
            f.write(remote_script_ps1)
            prod_upload_files.append(script_directory + remote_install_ps1_file)
            # upload wheel + scripts
            upload_file_to_ois(common_upload_files + prod_upload_files, siada_ois_env)
            print(f"Production install (macOS/Linux): curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/{siada_ois_env}/{remote_install_file} | bash")
            print(f"Production install (Windows PowerShell): powershell -NoProfile -ExecutionPolicy Bypass -Command \"iwr -UseBasicParsing 'https://bj.bcebos.com/prod-cnhb01-siada/cli-install/{siada_ois_env}/{remote_install_ps1_file}' | iex\"")

    if siada_ois_env.lower() == SiadaOis.TEST.value:
        with open(script_directory + test_remote_install_file, "w") as f:
            remote_script = (
                template_sh_content
                .replace("$env", siada_ois_env)
                .replace("$file_name", largest_whl_file)
            )
            f.write(remote_script)
            test_upload_files.append(script_directory + test_remote_install_file)
        # Windows PowerShell script for test
        with open(script_directory + test_remote_install_ps1_file, "w") as f:
            remote_script_ps1 = (
                template_ps1_content
                .replace("$env", siada_ois_env)
                .replace("$file_name", largest_whl_file)
            )
            f.write(remote_script_ps1)
            test_upload_files.append(script_directory + test_remote_install_ps1_file)
            # upload wheel + scripts
            upload_file_to_ois(common_upload_files + test_upload_files, siada_ois_env)
            print(f"Test install (macOS/Linux): curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/{siada_ois_env}/{test_remote_install_file} | bash")
            print(f"Test install (Windows PowerShell): powershell -NoProfile -ExecutionPolicy Bypass -Command \"iwr -UseBasicParsing 'https://bj.bcebos.com/prod-cnhb01-siada/cli-install/{siada_ois_env}/{test_remote_install_ps1_file}' | iex\"")

    print("**********************Packaging and upload completed!**********************")
    print(f"**********************Current siada version: {siada_version}**********************")
