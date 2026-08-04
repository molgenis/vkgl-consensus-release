# VKGL consensus release

This guide will explain every step in the VKGL data release process.
Please follow it step by step to guarantee consistent output for every release.
For the development of the VKGL data release process, please check [Development](#development-of-the-releasepipeline)

## Prerequisites
- Access/permissions for:
   * Nibbler
   * All umcg-vkgl-*LAB* accounts on nb-transfer.hpc.rug.nl
   * It's recommended to install a [GUI](https://docs.gcc.rug.nl/nibbler/dedicated-dt-server-external-collaborators/) to access the SFTP lab accounts
   * The [Download server](https://downloads.molgeniscloud.org)

## Preparation
1. Add the new release (yyyyMM) to the Releases table on https://vkgl.molgeniscloud.org/ReferenceLists
2. Check if the Labs, and related reference tables are still up-to-date
3. Get an empty server from the server list and set DNS to vkgl-release.molgenis.net
   - Set dtap to acc and include that this server will be used for the VKGL Consensus release in the description
   - Use the server list information of https://vkgl.molgeniscloud.org to fill in the other fields
4. Link DNS to the chosen server (or ask somebody with these privileges).
5. Update the server to the latest MOLGENIS version
6. Do a cross-restore from https://vkgl.molgeniscloud.org/ to https://vkgl-release.molgenis.net
7. After the restore, change the password on the release server back to the one in the Vault
8. Temporarily set the isOidcEnabled setting to false
9. Make sure you have a correctly configured key [ssh key forwarding](https://docs.gcc.rug.nl/nibbler/dedicated-dt-server-cluster-users/#configure-ssh-agent-forwarding).
10. Ssh with SSH agent forwarding enabled to Nibbler (use `-A` argument)
11. Go to `/groups/umcg-gcc/tmp02/projects/vkgl` and create a directory for this release (yyyyMM).
12. Get the latest version of the VKGL release pipeline:
    ```shell
    git clone https://github.com/molgenis/vkgl-consensus-release.git
    ```
13. Go to `vkgl-consensus-release`:
    ```shell
    cd vkgl-consensus-release
    ```
14. Check `rawLabFiles.txt` if the file names of the lab files correspond to the ones on nibbler-transfer
15. Fill in the right serverURL and credentials in `credentials.txt`. In case the pipeline runs as
    Slurm job, put the Slurm parameter to True.
16. Check if due to for example new file lay-out or a new lab-system a rerun from scratch for a certain
    lab needs to be done.
17. If so, first go to [release from scratch](#release-one-or-more-labs-from-scratch) otherwise
18. Otherwise, go straight to [VKGL Consensus release](#process-lab-data-normalise-and-create-consensus)

## Release one or more labs from scratch
1. Setup and install the VKGL release pipeline:
    ```shell
    module load Python
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    ```
2. If running locally, start `prepareScratchRun.py`. Otherwise
3. Start the `prepare-scratch-run.sh` Slurm job with parameters release and lab id (which can be found in the Labs table).
   Before starting the script check if the work allocation time (wall-time) is large enough.
   Default is half a day
    ```shell
    sbatch prepareScratchRun.sh yyyyMM _labID_
    ```
4. Save the batchID => see [SLURM.md](Slurm.md) for useful commands
5. Check regularly `prepare-scratch-run.out` or use one of the Slurm command to see if the job is still running
6. If the script has finished, check if indeed all data of the lab has been removed and the
    consensus is correctly updated. Otherwise, restore data from the production server again and
    restart the process.
7. If the data has been removed correctly, the new release can be started.

## Process lab data, normalise and create consensus
1. Setup and install the VKGL release pipeline (if not yet done):
    ```shell
    module load Python
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    ```

2. Make sure the script `dataRetriever.sh` is executable:
    ```shell
    chmod u+x dataRetriever.sh
    ```

3. Start `dataRetriever.sh` with parameter release (yyyyMM). This script can be skipped
    if the VKGL consensus release runs locally. In that case the Slurm parameter in
    `credentials.txt` needs to be set to False.
    ```shell
    ./dataRetriever.sh yyyyMM
    ```

4. Check `labDataRetrieval.out` if all data is successfully downloaded. Is so, the release can start!

5. In case of processing data for only one or a few labs, add this piece of Python code
    to `release_pipeline.py` after `for lab in self.config.labs:`:
   ```code
    if lab in ["aumc", "nki"]:
       continue
   ```

6. If running locally start `release_pipeline.py`. Otherwise
7. Start the `vkgl-consensus-release.sh` Slurm job with parameter release (yyyyMM).
   Before starting the script check if the work allocation time (walltime) is large enough.
   Default is one day, but for a full run from scratch about ten days are necessary
    ```shell
    sbatch vkgl-consensus-release.sh yyyyMM
    ```
8. Save the batchID => see [SLURM.md](Slurm.md) for useful commands
9. Check regularly `vkgl_conensus_release.out` or use one of the Slurm command if the job is still running

## Post-processing
1. Check if everything went OK:
   - Are errors shown in the log `vkgl_consensus_release.out`?
   - Create the markdown Summary with Checklist and check
   - Check DataSummary.md and add the content to the scrum board release ticket
   - Check variants in the Consensus table
   - Check the Public Consensus table
2. Update the MVL and Consensus version in /Public/settings/#/menu and /RawLabData/settings/#/menu
3. Update the Consensus version in /VKGL/settings/#/menu
4. Update the Counts page with data from the /Public/ConsensusCounts table
5. Upload the public consensus GRCh37 and GRCh38 files to the download server.
    How to can be found [here](https://umcgonline.sharepoint.com/:w:/r/sites/GeneticaSysteemgenetica-GCCOPS/_layouts/15/Doc.aspx?sourcedoc=%7BDF849902-8A23-4919-8AA0-7104B5EE5DBE%7D&file=WI%20MOLGENIS%20DM%20-%20Put%20data%20on%20download%20server.docx&action=default&mobileredirect=true&DefaultItemOpen=1)
6. Update the Downloads page accordingly.
7. Ask externals for review?
8. If everything looks fine:
   - Update the haproxy server:
       - Change the dns of vkgl-release.molgenis.net to vkgl.molgeniscloud.org
       - Remove (or rename) the vkgl.molgeniscloud.org dns from the current server
   - Update the server information in the server list of vkgl-release.molgenis.net:
      - Put dtap to prod
      - Adjust the vault location
      - Adjust the description
   - Put the old vkgl.molgeniscloud.org server to recycle
9. Notify the VKGL group

### Persist data on the `Nibbler` cluster prm03 folder
1. Go to `/groups/umcg-gcc/prm03/projects/VKGL/`
2. To be able to create folders and put data in this folder do: `sudo -u umcg-gcc-dm bash`
3. Create a new release folder with the name like `yyyyMM`.
4. Zip all files in tmp02/projects/VKGL/yyyyMM with
    ```shell
    zip -r VKGL_yyyyMM.zip *
    ```
5. Move the VKGL release run from Nibbler tmp02 to prm03
6. Create a `versions.txt` in `/groups/umcg-gcc/prm03/projects/VKGL/yyyyMM/` with the following content:
    ```text
    DATA:
    AUMC: source, date
    ErasmusMC: source, date
    LUMC: source, date
    NKI: source, date
    Radboud/MUMC: source, date
    UMCG: source, date
    UMCU: source, date

    Scripts:
    ~Link to GitHub location with date~
    ```

## Pipeline step by step explained:
### Per lab:
1. Data Acquisition
2. Data Ingestion
   Goal: Detect and process only new or updated variants
3. Normalisation
4. Identify new and updated variants
5. Upload into the VKGL database

### Create consensus
1. Merge lab data
2. Consensus classification
3. Upload consensus and public consensus into the VKGL database

### Quality checks
Goal: Ensure robustness, traceability, and data integrity throughout

## Development of the releasePipeline
### System requirements

- Python 3 (3.12.x)
- Git

### Initial one-time setup

Use virtual env to get a consistent python environment.

1. Clone the GitHub repository

   'git clone git@github.com:molgenis/vkgl-consensus-release'

2. Create a virtual python environment at the location of the scripts

   'cd vkgl-consensus-release'

   `python -m venv venv`

3. Activate the virtual python environment

   `source venv/bin/activate`

4. Install the script dependencies from requirements.txt file

   `pip install -r requirements.txt`

   More info see:

   mac: [https://www.youtube.com/watch?v=Kg1Yvry_Ydk](https://www.youtube.com/watch?v=Kg1Yvry_Ydk)

   windows: [https://www.youtube.com/watch?v=APOPm01BVrk](https://www.youtube.com/watch?v=APOPm01BVrk)

5. Define environment variables in .env, see .env_example

6. This project uses pre-commit and pipenv for the development workflow.
   Install pre-commit if you haven't already:
    ```shell
    pip install pre-commit
    ```

7. Install the git commit hooks:
    ```shell
    pre-commit install
    ```
