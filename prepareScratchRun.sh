#!/bin/bash
#SBATCH --job-name=prepareScratchRun
#SBATCH --output=prepare-scratch-run.out
#SBATCH --error=prepare-scratch-run.err
#SBATCH --time=12:00:00        # Default 1/2 day, if relevant adjust this
#SBATCH --mem=10G
#SBATCH --cpus-per-task=4
#SBATCH --nodes=1
#SBATCH --open-mode=append
#SBATCH --export=NONE
#SBATCH --get-user-env=60L

if [[ $1 -eq 0 ]] ; then
    echo "Please enter release yyyyMM"
    exit 1
fi

release=$1

if [[ -z "$2" ]] ; then
    echo "Please enter the lab that will run from scratch"
    exit 1
fi

lab=$2

echo "Start preparing scratch run for ${lab} in ${release} release"

module purge

module load Python
source /groups/umcg-gcc/tmp02/projects/vkgl/$release/vkgl-consensus-release/venv/bin/activate

echo Preparing scratch run started at `date`
python --version
cd /groups/umcg-gcc/tmp02/projects/vkgl/$release/vkgl-consensus-release
python -u prepareScratchRun.py ${lab}
echo Preparing scratch run finished at `date`
