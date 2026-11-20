import os
import tempfile

os.environ["VC_RUNS"] = tempfile.mkdtemp(prefix="vc_test_runs_")   # tests never write into the owner's real runs/
