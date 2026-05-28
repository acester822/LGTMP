## Silent install
To do a silent install of Alloy on Windows, perform the following steps.

### Navigate to the latest release on GitHub. https://github.com/grafana/alloy/releases/latest
https://github.com/grafana/alloy/releases/download/v1.2.0/alloy-installer-windows-amd64.exe.zip


### Scroll down to the Assets section.

### Download the file called alloy-installer-windows-amd64.exe.zip.

### Unzip the downloaded file.

### Run the following command in PowerShell or Command Prompt:

```cmd
"C:\Users\<user here>\Desktop\alloy-installer-windows-amd64.exe\alloy-installer-windows-amd64.exe" /S /DISABLEREPORTING=yes
```

Replace the following:
<PATH_TO_INSTALLER>: The path where the unzipped installer executable is located.

### Silent install options
/CONFIG=<path> Path to the configuration file. Default: $INSTDIR\config.alloy
/DISABLEREPORTING=<yes|no> Disable data collection. Default: no
/DISABLEPROFILING=<yes|no> Disable profiling endpoint. Default: no
/ENVIRONMENT="KEY=VALUE\0KEY2=VALUE2" Define environment variables for Windows Service. Default: ``

### Service Configuration
Alloy uses the Windows Registry HKLM\Software\GrafanaLabs\Alloy for service configuration.
Arguments (Type REG_MULTI_SZ) Each value represents a binary argument for alloy binary.
Environment (Type REG_MULTI_SZ) Each value represents a environment value KEY=VALUE for alloy binary.

### Uninstall
You can uninstall Alloy with Windows Remove Programs or %PROGRAMFILES64%\GrafanaLabs\Alloy\uninstaller.exe. Uninstalling Alloy stops the service and removes it from disk. This includes any configuration files in the installation directory.

Alloy can also be silently uninstalled by running uninstall.exe /S as Administrator.