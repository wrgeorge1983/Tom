# Adapters and Drivers Reference

Tom supports two network automation libraries (adapters): **Netmiko** and **Scrapli**. The drivers available depend on what these libraries support - Tom just passes the driver name through to them.

## Listing Drivers

To get the current list of available drivers from your installed version:

```bash
cd services/worker
uv run python -m tom_worker.adapters.main
```

## Reference: Supported Drivers

The following lists are exported from Netmiko and Scrapli for convenience. For the authoritative and up-to-date list, use the command above or consult the respective library documentation:

- [Netmiko Platforms](https://github.com/ktbyers/netmiko/blob/develop/PLATFORMS.md)
- [Scrapli](https://github.com/carlmontanari/scrapli) - See their documentation for supported platforms

## Scrapli Drivers

Scrapli is async and generally faster, but supports fewer platforms:

| Driver | Platform |
|--------|----------|
| `arista_eos` | Arista EOS |
| `cisco_iosxe` | Cisco IOS-XE |
| `cisco_iosxr` | Cisco IOS-XR |
| `cisco_nxos` | Cisco NX-OS |
| `juniper_junos` | Juniper Junos |

## Netmiko Drivers

Netmiko supports a wide range of platforms:

| Driver | Platform |
|--------|----------|
| `a10` | A10 |
| `accedian` | Accedian |
| `adtran_os` | Adtran OS |
| `adva_fsp150f2` | ADVA FSP 150F2 |
| `adva_fsp150f3` | ADVA FSP 150F3 |
| `alaxala_ax26s` | AlaxalA AX26S |
| `alaxala_ax36s` | AlaxalA AX36S |
| `alcatel_aos` | Alcatel AOS |
| `alcatel_sros` | Alcatel SR OS |
| `allied_telesis_awplus` | Allied Telesis AW+ |
| `apresia_aeos` | Apresia AEOS |
| `arista_eos` | Arista EOS |
| `arris_cer` | Arris CER |
| `aruba_aoscx` | Aruba AOS-CX |
| `aruba_os` | Aruba OS |
| `aruba_osswitch` | Aruba OS Switch |
| `aruba_procurve` | Aruba ProCurve |
| `asterfusion_asternos` | Asterfusion AsternOS |
| `audiocode_66` | AudioCodes 66 |
| `audiocode_72` | AudioCodes 72 |
| `audiocode_shell` | AudioCodes Shell |
| `avaya_ers` | Avaya ERS |
| `avaya_vsp` | Avaya VSP |
| `bintec_boss` | BinTec BOSS |
| `broadcom_icos` | Broadcom ICOS |
| `brocade_fastiron` | Brocade FastIron |
| `brocade_fos` | Brocade FOS |
| `brocade_netiron` | Brocade NetIron |
| `brocade_nos` | Brocade NOS |
| `brocade_vdx` | Brocade VDX |
| `brocade_vyos` | Brocade VyOS |
| `calix_b6` | Calix B6 |
| `casa_cmts` | Casa CMTS |
| `cdot_cros` | CDOT CROS |
| `centec_os` | Centec OS |
| `checkpoint_gaia` | Check Point GAiA |
| `ciena_saos` | Ciena SAOS |
| `ciena_saos10` | Ciena SAOS 10 |
| `ciena_waveserver` | Ciena Waveserver |
| `cisco_apic` | Cisco APIC |
| `cisco_asa` | Cisco ASA |
| `cisco_ftd` | Cisco FTD |
| `cisco_ios` | Cisco IOS |
| `cisco_nxos` | Cisco NX-OS |
| `cisco_s200` | Cisco S200 |
| `cisco_s300` | Cisco S300 |
| `cisco_tp` | Cisco TelePresence |
| `cisco_viptela` | Cisco Viptela |
| `cisco_wlc` | Cisco WLC |
| `cisco_xe` | Cisco IOS-XE |
| `cisco_xr` | Cisco IOS-XR |
| `cloudgenix_ion` | CloudGenix ION |
| `corelight_linux` | Corelight Linux |
| `coriant` | Coriant |
| `cumulus_linux` | Cumulus Linux |
| `dell_dnos9` | Dell DNOS9 |
| `dell_force10` | Dell Force10 |
| `dell_isilon` | Dell Isilon |
| `dell_os10` | Dell OS10 |
| `dell_os6` | Dell OS6 |
| `dell_os9` | Dell OS9 |
| `dell_powerconnect` | Dell PowerConnect |
| `dell_sonic` | Dell SONiC |
| `digi_transport` | Digi Transport |
| `dlink_ds` | D-Link DS |
| `edgecore_sonic` | Edgecore SONiC |
| `ekinops_ek360` | Ekinops EK360 |
| `eltex` | Eltex |
| `eltex_esr` | Eltex ESR |
| `endace` | Endace |
| `enterasys` | Enterasys |
| `ericsson_ipos` | Ericsson IPOS |
| `ericsson_mltn63` | Ericsson MLTN63 |
| `ericsson_mltn66` | Ericsson MLTN66 |
| `extreme` | Extreme |
| `extreme_ers` | Extreme ERS |
| `extreme_exos` | Extreme EXOS |
| `extreme_netiron` | Extreme NetIron |
| `extreme_nos` | Extreme NOS |
| `extreme_slx` | Extreme SLX |
| `extreme_tierra` | Extreme Tierra |
| `extreme_vdx` | Extreme VDX |
| `extreme_vsp` | Extreme VSP |
| `extreme_wing` | Extreme Wing |
| `f5_linux` | F5 Linux |
| `f5_ltm` | F5 LTM |
| `f5_tmsh` | F5 TMSH |
| `fiberstore_fsos` | Fiberstore FSOS |
| `fiberstore_fsosv2` | Fiberstore FSOS v2 |
| `fiberstore_networkos` | Fiberstore NetworkOS |
| `flexvnf` | FlexVNF |
| `fortinet` | Fortinet |
| `garderos_grs` | Garderos GRS |
| `generic` | Generic |
| `generic_termserver` | Generic Terminal Server |
| `h3c_comware` | H3C Comware |
| `hillstone_stoneos` | Hillstone StoneOS |
| `hp_comware` | HP Comware |
| `hp_procurve` | HP ProCurve |
| `huawei` | Huawei |
| `huawei_olt` | Huawei OLT |
| `huawei_smartax` | Huawei SmartAX |
| `huawei_smartaxmmi` | Huawei SmartAX MMI |
| `huawei_vrp` | Huawei VRP |
| `huawei_vrpv8` | Huawei VRP v8 |
| `infinera_packet` | Infinera Packet |
| `ipinfusion_ocnos` | IP Infusion OcNOS |
| `juniper` | Juniper |
| `juniper_junos` | Juniper Junos |
| `juniper_screenos` | Juniper ScreenOS |
| `keymile` | Keymile |
| `keymile_nos` | Keymile NOS |
| `lancom_lcossx4` | LANCOM LCOS SX4 |
| `linux` | Linux |
| `maipu` | Maipu |
| `mellanox` | Mellanox |
| `mellanox_mlnxos` | Mellanox MLNX-OS |
| `mikrotik_routeros` | MikroTik RouterOS |
| `mikrotik_switchos` | MikroTik SwitchOS |
| `mrv_lx` | MRV LX |
| `mrv_optiswitch` | MRV OptiSwitch |
| `nec_ix` | NEC IX |
| `netapp_cdot` | NetApp cDOT |
| `netgear_prosafe` | Netgear ProSafe |
| `netscaler` | NetScaler |
| `nokia_srl` | Nokia SR Linux |
| `nokia_sros` | Nokia SR OS |
| `oneaccess_oneos` | OneAccess OneOS |
| `ovs_linux` | OVS Linux |
| `paloalto_panos` | Palo Alto PAN-OS |
| `pluribus` | Pluribus |
| `quanta_mesh` | Quanta Mesh |
| `rad_etx` | RAD ETX |
| `raisecom_roap` | Raisecom ROAP |
| `ruckus_fastiron` | Ruckus FastIron |
| `ruijie_os` | Ruijie OS |
| `silverpeak_vxoa` | Silver Peak VX-OA |
| `sixwind_os` | 6WIND OS |
| `sophos_sfos` | Sophos SFOS |
| `supermicro_smis` | Supermicro SMIS |
| `telcosystems_binos` | Telco Systems binOS |
| `teldat_cit` | Teldat CIT |
| `tplink_jetstream` | TP-Link JetStream |
| `ubiquiti_edge` | Ubiquiti Edge |
| `ubiquiti_edgerouter` | Ubiquiti EdgeRouter |
| `ubiquiti_edgeswitch` | Ubiquiti EdgeSwitch |
| `ubiquiti_unifiswitch` | Ubiquiti UniFi Switch |
| `vertiv_mph` | Vertiv MPH |
| `vyatta_vyos` | Vyatta VyOS |
| `vyos` | VyOS |
| `watchguard_fireware` | WatchGuard Fireware |
| `yamaha` | Yamaha |
| `zte_zxros` | ZTE ZXROS |
| `zyxel_os` | Zyxel OS |

## Driver Naming Differences

Note that some drivers have different names between adapters:

| Platform | Netmiko | Scrapli |
|----------|---------|---------|
| Cisco IOS-XE | `cisco_xe` | `cisco_iosxe` |
| Cisco IOS-XR | `cisco_xr` | `cisco_iosxr` |
