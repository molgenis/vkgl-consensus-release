### Run VKGL consensus release pipeline on Nibbler using the Slurm workload manager
General Slurm information:
https://docs.gcc.rug.nl/nibbler/analysis/

More detailed information on using Python virtual environment inside slurm job can be found [here](https://docs.gcc.rug.nl/nibbler/python/#using-python-virtual-environment-inside-slurm-job)

**Check Slurm jobs:**
- Check if the job has started/still runs with:
    ```shell
    `squeue -j [JOBID]`
    ```
- More detailed information about the job:
    ```shell
    `sacct -j [JOBID] --format=JobID,JobName,Partition,State,Start,End,Elapsed,ExitCode`
    ```
- **Output and error messages:**

    - In the `.out` file of the job the normal print-statements from the script can be found.

    - In the `.err` file are any possible error messages during processing.

- **Check job on the node where it runs:**

    - The node where the Slurm job runs can be found with in the `NODELIST(REASON)` column:

      `squeue -j [JOBID]`

    - SSH to the node:

      `ssh [nodename]`

- **Check if of the release-pipeline.py job actually runs on the node:**
  `ps -u [username] -f | grep python`

  This shows the active Python processes of the user, to confirm that `release-pipeline.py` is still running.
