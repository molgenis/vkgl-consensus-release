#!/bin/bash
#SBATCH --job-name=vkgl-consensus-release
#SBATCH --output=vkgl-consensus-release.out
#SBATCH --error=vkgl-consensus-release.err
#SBATCH --time=24:00:00        # Default 1 day, depending on if it's a full run or just new/updates adjust this
#SBATCH --mem=10G
#SBATCH --cpus-per-task=4
#SBATCH --nodes=1
#SBATCH --open-mode=append
#SBATCH --export=NONE
#SBATCH --get-user-env=60L

release=$1

if [[ $1 -eq 0 ]] ; then
    echo "Please enter release yyyyMM"
    exit 1
fi

echo "Start VKGL ${release} Consensus Release"

module purge

module load Python
source /groups/umcg-gcc/tmp02/projects/vkgl/$release/vkgl-consensus-release/venv/bin/activate

echo VKGL Consensus release started at `date`
python --version
cd /groups/umcg-gcc/tmp02/projects/vkgl/$release/vkgl-consensus-release
python -u release_pipeline.py
echo VKGL Consensus release finished at `date`
