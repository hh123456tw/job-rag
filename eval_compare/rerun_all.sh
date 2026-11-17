set -x
export JOB_RAG_CORPUS='C:\claude\aipe04期末\履歷\廠商深查' JOB_RAG_MODELS='C:\claude\aipe04期末\job-rag\models' JOB_RAG_CACHE="$PWD/.cache_new"
python -X utf8 -m job_rag.evalset --write-md
python -X utf8 -m job_rag.evaluate --method all --detect --dedupe > dist/logs/methods.log 2>&1; echo methods $?
python -X utf8 -m job_rag.evaluate --toggles > dist/logs/tog.log 2>&1; echo tog $?
python -X utf8 -m job_rag.evaluate --toggles --method bm25 --out eval/results_toggles_bm25.txt > dist/logs/tog2.log 2>&1; echo tog2 $?
python -X utf8 -m job_rag.evaluate --method bm25 > eval/results_bm25.txt 2>dist/logs/bm25.err; echo bm25 $?
python -X utf8 eval/run_real.py > dist/logs/real.log 2>&1; echo real $?
python -X utf8 eval/run_cross.py > dist/logs/cross.log 2>&1; echo cross $?
python -X utf8 eval/run_heldout.py > dist/logs/held.log 2>&1; echo held $?
echo ALLDONE
