import subprocess

command = f"/usr/bin/ps -aux | grep main.py"
result = subprocess.run(command, shell=True, capture_output=True, text=True)
pid = result.stdout.split(' ')[2]
print(f"kill {pid}")
subprocess.run(f"kill {pid}", shell=True, capture_output=True, text=True)