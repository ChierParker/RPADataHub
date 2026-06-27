import os, subprocess, sys, time

base = r"c:\Users\JackPeesao\Desktop\EcomIQ-RPA"
venv_path = os.path.join(base, ".venv")

# Step 1: Kill lingering venv processes and delete
if os.path.exists(venv_path):
    for _ in range(3):
        try:
            import shutil
            shutil.rmtree(venv_path)
            print("✅ Old .venv deleted")
            break
        except PermissionError:
            print(f"⚠ venv locked, retrying...")
            time.sleep(1)

if os.path.exists(venv_path):
    print("❌ Could not delete .venv - please close VS Code terminal and re-run")
    sys.exit(1)

# Step 2: Create new venv
result = subprocess.run(
    [sys.executable, "-m", "venv", ".venv"],
    cwd=base, capture_output=True, text=True, timeout=60
)
if result.returncode == 0:
    print("✅ New .venv created")
else:
    print(f"❌ venv creation failed: {result.stderr}")
    sys.exit(1)

# Step 3: Install requirements
pip_exe = os.path.join(venv_path, "Scripts", "pip.exe")
result = subprocess.run(
    [pip_exe, "install", "-r", "requirements.txt"],
    cwd=base, timeout=300
)
print(f"✅ requirements.txt installed" if result.returncode == 0 else f"⚠ pip exit: {result.returncode}")

print("\n🎉 Venv rebuild complete! Run: start.bat")

