# PLC Test Suite

A GUI-based testing tool for Allen-Bradley PlantPAx simulations using EtherNet/IP communication.

## Features

- **Tag Monitor**: Track multiple PLC tags in real-time with auto-refresh
- **Quick Write**: Easily write values to individual tags
- **Simulation Control**: Enable/disable PlantPAx simulation mode for devices
- **User-Friendly GUI**: No command-line expertise required
- **PlantPAx Integration**: Built-in support for common PlantPAx tag structures

## Installation

### Prerequisites
- Python 3.8 or higher
- Allen-Bradley PLC with EtherNet/IP communication
- Network access to the PLC

### Method 1: Install from GitHub (Recommended for team distribution)

```bash
pip install git+https://github.com/joelryan22/plc-test-suite.git
```

Then run:
```bash
plc-test-suite
```

### Method 2: Local Development Installation

1. Clone the repository:
```bash
git clone https://github.com/joelryan22/plc-test-suite.git
cd plc-test-suite
```

2. Install in editable mode:
```bash
pip install -e .
```

3. Run the application:
```bash
plc-test-suite
```

### Method 3: Standalone Executable (Coming Soon)

For non-technical users, download the pre-built executable from the Releases page.

## Usage

### Connecting to PLC

1. Launch the application: `plc-test-suite`
2. Enter your PLC's IP address (e.g., `192.168.1.10`)
3. Click **Connect**

### Tag Monitor Tab

Monitor multiple tags in real-time:

1. Enter a tag name (e.g., `Valve_001.inp_sim`)
2. Click **Add Tag**
3. Click **Refresh Now** to read current values
4. Enable **Auto-Refresh** for continuous monitoring (1-second interval)

### Quick Write Tab

Write values to individual tags:

1. Enter tag name (e.g., `LT_Tank_001.inp_sim`)
2. Enter value (e.g., `75.5` or `True`)
3. Select data type or leave as **Auto-detect**
4. Click **Write Tag**

### Simulation Control Tab

Enable/disable PlantPAx simulation mode:

1. Enter device name (e.g., `Valve_001`)
2. Click **Enable Simulation** or **Disable Simulation**
3. The tool automatically writes to `{device}.cfg_sim`

## PlantPAx Tag Reference

Common PlantPAx simulation tags:

| Tag | Type | Description |
|-----|------|-------------|
| `.cfg_sim` | BOOL | Enable/disable simulation mode |
| `.inp_sim` | REAL/BOOL | Simulated input value |
| `.out_sim` | REAL/BOOL | Simulated output value |
| `.inp_simZSO` | BOOL | Valve open limit switch |
| `.inp_simZSC` | BOOL | Valve closed limit switch |

### Example Workflow

**Simulating a Tank Fill Operation:**

1. **Enable simulation for devices:**
   - Device: `Valve_FillValve`
   - Device: `LT_Tank_Level`
   - Device: `FT_Flow_Inlet`

2. **Monitor tags:**
   - Add: `Valve_FillValve.out_cv` (valve command)
   - Add: `LT_Tank_Level.inp_sim` (level)
   - Add: `FT_Flow_Inlet.inp_sim` (flow)
   - Enable Auto-Refresh

3. **Simulate flow when valve opens:**
   - Tag: `FT_Flow_Inlet.inp_sim`
   - Value: `200.0` (GPM)
   
4. **Simulate level rising:**
   - Use Python script or manual writes to increment `LT_Tank_Level.inp_sim`

## Future Enhancements

- [ ] Test routine creation (save/load sequences)
- [ ] Automatic simulation logic (e.g., tank fill/drain calculations)
- [ ] Visual device relationships
- [ ] Batch tag operations
- [ ] Historical data logging
- [ ] Export test results

## Development

### Project Structure

```
plc-test-suite/
├── plc_test_suite/
│   ├── __init__.py
│   ├── main.py              # GUI application
│   └── plc_connection.py    # PLC communication
├── tests/
├── pyproject.toml
└── README.md
```

### Running Tests

```bash
pytest tests/
```

### Building Standalone Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name="PLC-Test-Suite" plc_test_suite/main.py
```

The executable will be in `dist/PLC-Test-Suite.exe`

## Dependencies

- `pycomm3` - Allen-Bradley PLC communication
- `PyQt6` - GUI framework

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

Internal tool - no standard licensing.

## Support

There is none (for now).

## Acknowledgments

- Built with [pycomm3](https://github.com/ottowayi/pycomm3)
- GUI built with PyQt6
