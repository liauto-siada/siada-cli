from unittest import IsolatedAsyncioTestCase


class TestDatasetDownload(IsolatedAsyncioTestCase):

    def test_download_swe_bench_dataset(self):
        from siada.swe import load_hugginface_swe_bench_dataset
        dataset = load_hugginface_swe_bench_dataset("princeton-nlp/SWE-bench_Lite", "test")
        print(dataset)