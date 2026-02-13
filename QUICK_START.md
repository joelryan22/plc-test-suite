# Quick Start Guide - PLC Test Suite

## Getting Your Project Ready for GitHub

### 1. Initial Setup (One Time)

```bash
# Navigate to where you want the project
cd ~/Documents/projects

# Clone/create your project directory
mkdir plc-test-suite
cd plc-test-suite

# Copy the files from this template into your directory
# (or create them manually using the files provided)

# Create a virtual environment (recommended)
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install in development mode
pip install -e .
```

### 2. Test Locally

```bash
# Run the application
plc-test-suite

# Or run directly
python -m plc_test_suite.main
```

### 3. Push to GitHub

```bash
# Initialize git repository
git init

# Add all files
git add .

# Make first commit
git commit -m "Initial commit - PLC Test Suite v0.1"

# Create a new repository on GitHub (github.com)
# Then link it:
git remote add origin https://github.com/yourusername/plc-test-suite.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### 4. Let Your Coworkers Install

They can now install directly from GitHub:

```bash
pip install git+https://github.com/yourusername/plc-test-suite.git
```

Then run:
```bash
plc-test-suite
```

## Making Updates

When you make changes:

```bash
# Make your changes to the code

# Test locally
plc-test-suite

# Commit changes
git add .
git commit -m "Added feature X"

# Push to GitHub
git push

# Tell coworkers to update:
# pip install --upgrade git+https://github.com/yourusername/plc-test-suite.git
```

## Creating a Standalone Executable

When you're ready to create a .exe file:

```bash
# Install PyInstaller
pip install pyinstaller

# Build the executable
pyinstaller --onefile --windowed --name="PLC-Test-Suite" plc_test_suite/main.py

# The .exe will be in dist/PLC-Test-Suite.exe
# Share this file - no Python installation needed!
```

## Troubleshooting

**"Module not found" errors:**
- Make sure you're in the virtual environment (you should see `(venv)` in your terminal)
- Run `pip install -e .` again

**Can't connect to PLC:**
- Verify the IP address is correct
- Check network connectivity: `ping 192.168.1.10`
- Ensure PLC has EtherNet/IP enabled
- Check firewall settings

**GUI doesn't start:**
- Make sure PyQt6 installed: `pip install PyQt6`
- On Linux, you might need: `sudo apt-get install python3-pyqt6`

## Next Steps

1. **Test with your actual PLC** - update the default IP in the code
2. **Add your specific PlantPAx devices** - customize the simulation control
3. **Build test routines** - create reusable test sequences
4. **Add documentation** - document your specific tag naming conventions

## Development Workflow

```bash
# Always work in a branch for new features
git checkout -b feature/new-feature

# Make changes, test, commit
git add .
git commit -m "Description of changes"

# Merge back to main when ready
git checkout main
git merge feature/new-feature
git push
```
