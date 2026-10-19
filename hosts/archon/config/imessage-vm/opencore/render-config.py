#!/usr/bin/env python3
"""Render the imessage-vm OpenCore config.plist.

Base: LongQT-sea/OpenCore-ISO v0.7 EFI_RELEASE config (the QEMU config that
OSX-KVM 4c378a4 adopted). Changes are deliberate and listed in README.md:
VMHide after Lilu, no VoodooPS2 (USB input only), builtin text picker (no
OpenCanopy resources), and the persistent identity from identity.env.

usage: render-config.py BASE_PLIST IDENTITY_ENV OUT_PLIST
"""
import plistlib
import re
import sys


def load_identity(path):
    ident = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            ident[key] = value.strip().strip('"')
    required = ("SMBIOS_MODEL", "SERIAL", "MLB", "SYSTEM_UUID", "ROM")
    missing = [k for k in required if not ident.get(k)]
    if missing:
        sys.exit(f"identity file lacks {', '.join(missing)}")
    if not re.fullmatch(r"[0-9a-f]{12}", ident["ROM"]):
        sys.exit("ROM must be 12 lowercase hex digits")
    return ident


def kext(bundle, executable, comment, min_kernel=""):
    return {
        "Arch": "x86_64", "BundlePath": bundle, "Comment": comment, "Enabled": True,
        "ExecutablePath": executable, "MaxKernel": "", "MinKernel": min_kernel,
        "PlistPath": "Contents/Info.plist",
    }


def main(base_path, identity_path, out_path):
    config = plistlib.load(open(base_path, "rb"))
    ident = load_identity(identity_path)

    adds = [k for k in config["Kernel"]["Add"] if not k["BundlePath"].startswith("VoodooPS2")]
    names = [k["BundlePath"] for k in adds]
    if names != ["Lilu.kext", "VirtualSMC.kext", "WhateverGreen.kext", "AppleMCEReporterDisabler.kext"]:
        sys.exit(f"unexpected base kext list: {names}")
    # Lilu plug-ins must load after Lilu; VMHide hides kern.hv_vmm_present from
    # Apple Account processes on macOS 15 (see README).
    adds.insert(1, kext("VMHide.kext", "Contents/MacOS/VMHide", "VMHide 2.0.0"))
    config["Kernel"]["Add"] = adds

    config["UEFI"]["Drivers"] = [d for d in config["UEFI"]["Drivers"] if d["Path"] != "OpenCanopy.efi"]
    for driver in config["UEFI"]["Drivers"]:
        driver.setdefault("HideVerbose", False)  # key added in OpenCore 1.0.8
    boot = config["Misc"]["Boot"]
    boot["PickerMode"] = "Builtin"
    boot["Timeout"] = 5

    security = config["Misc"]["Security"]
    if security["DmgLoading"] != "Signed":
        sys.exit("base config no longer requires signed DMG loading")

    generic = config["PlatformInfo"]["Generic"]
    generic["SystemProductName"] = ident["SMBIOS_MODEL"]
    generic["SystemSerialNumber"] = ident["SERIAL"]
    generic["MLB"] = ident["MLB"]
    generic["SystemUUID"] = ident["SYSTEM_UUID"]
    generic["ROM"] = bytes.fromhex(ident["ROM"])

    with open(out_path, "wb") as out:
        plistlib.dump(config, out, sort_keys=True)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
