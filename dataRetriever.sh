# Separate procedure when running the VKGL consensus release via a Slurm job as this part
# contains rsync procedures which don't work properly within Slurm unless separate private/public keys
# are generated and included on Nibbler.

release=$1

if [[ $1 -eq 0 ]] ; then
    echo "Please enter release yyyyMM"
    exit 1
fi

echo "Get VKGL raw lab data"

module purge

module load Python
source /groups/umcg-gcc/tmp02/projects/vkgl/$release/vkgl-consensus-release/venv/bin/activate

echo Raw lab data retrieval started at `date`
python --version
cd /groups/umcg-gcc/tmp02/projects/vkgl/$release/vkgl-consensus-release
python -u labDataRetriever.py > labDataRetrieval.out
echo Raw lab data retrieval finished at `date`
