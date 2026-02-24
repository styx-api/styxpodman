# Podman/Apptainer Runner for Styx compiled wrappers

[![Build](https://github.com/styx-api/styxpodman/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/styx-api/styxpodman/actions/workflows/test.yaml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/styx-api/styxpodman/branch/main/graph/badge.svg?token=22HWWFWPW5)](https://codecov.io/gh/styx-api/styxpodman)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![stability-stable](https://img.shields.io/badge/stability-stable-green.svg)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/styx-api/styxpodman/blob/main/LICENSE)
[![pages](https://img.shields.io/badge/api-docs-blue)](https://styx-api.github.io/styxpodman)

`styxpodman` is a Python package that provides Podman integration for Styx compiled wrappers. It allows you to run Styx functions within Podman containers, offering improved isolation and reproducibility for your workflows.

## Installation

You can install `styxpodman` using pip:

```Python
pip install styxpodman
```

## Usage

```Python
from styxdefs import set_global_runner
from styxpodman import PodmanRunner

# Initialize the PodmanRunner
runner = PodmanRunner()

# Set the global runner for Styx
set_global_runner(runner)

# Now you can use any Styx functions as usual, and they will run in Podman containers
```

## Advanced Configuration

The `PodmanRunner` class accepts several parameters for advanced configuration:

- `image_overrides`: A dictionary to override container image tags
- `podman_executable`: Path to the Podman executable (default: `"podman"`)
- `data_dir`: Directory for temporary data storage
- `environ`: Environment variables to set in the container

Example:

```python
runner = PodmanRunner(
    image_overrides={"python:3.9": "my-custom-python:3.9"},
    podman_executable="/usr/local/bin/podman",
    data_dir="/tmp/styx_data",
    environ={"PYTHONPATH": "/app/lib"}
)
```

## Error Handling

`styxpodman` provides a custom error class, `StyxPodmanError`, which is raised when a Podman execution fails. This error includes details about the return code, command arguments, and Podman arguments for easier debugging.

## Contributing

Contributions to `styxpodman` are welcome! Please refer to the [GitHub repository](https://github.com/styx-api/styxpodman) for information on how to contribute, report issues, or submit pull requests.

## License

`styxpodman` is released under the MIT License. See the LICENSE file for details.

## Documentation

For detailed API documentation, please visit our [API Docs](https://styx-api.github.io/styxpodman).

## Support

If you encounter any issues or have questions, please open an issue on the [GitHub repository](https://github.com/styx-api/styxpodman).

## Requirements

- Python 3.10+
- Podman or Apptainer installed and running on your system

## Comparison with [`styxdocker`](https://github.com/styx-api/styxdocker)

While [`styxdocker`](https://github.com/styx-api/styxdocker) and [`styxpodman`](https://github.com/styx-api/styxpodman) serve similar purposes, they have some key differences:

- Container Technology: `styxdocker` uses Docker, while `styxpodman` uses Podman/Apptainer.
- Platform Support: `styxdocker` works on Windows, Linux, and macOS, whereas `styxpodman` is not supported on Windows.
- User Permissions: `styxdocker` can run containers as the current user on POSIX systems, which can help with file permission issues.

Choose the package that best fits your infrastructure and requirements.
