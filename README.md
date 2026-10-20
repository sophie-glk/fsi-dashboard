# FSI Dashboard (Python / PyQt6)

This repository contains the **FSI Dashboard**, completely rewritten in Python using **PyQt6**.

## Getting Started

Follow these steps to set up the environment and run the application on your Raspberry Pi:

### 1. Setup a Virtual Environment (Recommended)
To prevent conflicts with system packages, create and activate a isolated environment:
```bash
python -m venv --system-site-packages venv
source venv/bin/activate
```
*(Note: `--system-site-packages` allows the virtual environment to use pre-installed Pi-specific libraries if needed, without altering them).*

### 2. Install Dependencies
Install the required packages safely within the environment:
```bash
pip install -r requirements.txt
```

### 3. Launch the Application
Run the main script to start the dashboard:
```bash
python dashboard.py
```

