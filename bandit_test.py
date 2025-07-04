import subprocess

# Bandit will definitely flag this
subprocess.call("ls", shell=True)
