#!/bin/bash
    set -e

    # Random sleep to avoid concurrent network connection errors
    SLEEP_TIME=$((RANDOM % 56 + 5))  # Random number between 5 and 60
    # echo "Sleeping for $SLEEP_TIME seconds to avoid concurrent connections..."
    # sleep $SLEEP_TIME

    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
    conda config --set show_channel_urls yes

    # export http_proxy="http://127.0.0.1:7890"
    # export https_proxy="http://127.0.0.1:7890"
    # export HTTP_PROXY="http://127.0.0.1:7890"
    # export HTTPS_PROXY="http://127.0.0.1:7890"

    # 将预装环境注册到 conda
    source $(conda info --base)/etc/profile.d/conda.sh
    ln -sf /siada-agenthub/python312_standalone $(conda info --base)/envs/python312_base

    # 使用 conda 克隆环境（这会自动处理路径问题）
    conda create -p /tmp/siada_env_django__django-11001 --clone python312_base -y

    # mkdir /tmp/siada_env_django__django-11179/
    # cp -r /siada-agenthub/envs/* /tmp/siada_env_django__django-11001/
    # conda create -p /tmp/siada_env_django__django-11001 python=3.12 -y
    conda activate /tmp/siada_env_django__django-11001
    pip install /siada-agenthub/siada_agenthub-0.0.0.tar.gz

TEMP_DESC="/tmp/description_django__django-11001.txt"
cat > "$TEMP_DESC" << 'SIADA_1024_EOF'
Incorrect removal of order_by clause created as multiline RawSQL
Description
	
Hi.
The SQLCompiler is ripping off one of my "order by" clause, because he "thinks" the clause was already "seen" (in SQLCompiler.get_order_by()). I'm using expressions written as multiline RawSQLs, which are similar but not the same. 
The bug is located in SQLCompiler.get_order_by(), somewhere around line computing part of SQL query without ordering:
without_ordering = self.ordering_parts.search(sql).group(1)
The sql variable contains multiline sql. As a result, the self.ordering_parts regular expression is returning just a line containing ASC or DESC words. This line is added to seen set, and because my raw queries have identical last lines, only the first clasue is returing from SQLCompiler.get_order_by().
As a quick/temporal fix I can suggest making sql variable clean of newline characters, like this:
sql_oneline = ' '.join(sql.split('\n'))
without_ordering = self.ordering_parts.search(sql_oneline).group(1)
Note: beware of unicode (Py2.x u'') and EOL dragons (\r).
Example of my query:
	return MyModel.objects.all().order_by(
		RawSQL('''
			case when status in ('accepted', 'verification')
				 then 2 else 1 end''', []).desc(),
		RawSQL('''
			case when status in ('accepted', 'verification')
				 then (accepted_datetime, preferred_datetime)
				 else null end''', []).asc(),
		RawSQL('''
			case when status not in ('accepted', 'verification')
				 then (accepted_datetime, preferred_datetime, created_at)
				 else null end''', []).desc())
The ordering_parts.search is returing accordingly:
'				 then 2 else 1 end)'
'				 else null end'
'				 else null end'
Second RawSQL with a				 else null end part is removed from query.
The fun thing is that the issue can be solved by workaround by adding a space or any other char to the last line. 
So in case of RawSQL I can just say, that current implementation of avoiding duplicates in order by clause works only for special/rare cases (or does not work in all cases). 
The bug filed here is about wrong identification of duplicates (because it compares only last line of SQL passed to order by clause).
Hope my notes will help you fixing the issue. Sorry for my english.

SIADA_1024_EOF

    cd /testbed
    conda deactivate
    conda activate testbed
    /tmp/siada_env_django__django-11001/bin/siada-cli --bugfix --prompt "$(cat "$TEMP_DESC")"
    conda env remove -p /tmp/siada_env_django__django-11001 -y
    rm "$TEMP_DESC"
    rm -rf /tmp/siada_env_django__django-11001
    