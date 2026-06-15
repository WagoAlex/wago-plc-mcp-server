# Edge Controller — WDA Parameter List (FW build 31)

**Device:** 192.168.42.124 (Edge Controller)  
**Recorded:** 2026-06-15  
**Firmware hint:** 04.09.01 (31) — not yet confirmed from device; verify via `0-0-version-firmwareversion`  
**Total in pool:** 394  
**Captured here:** 392 (98.98 %) — 2 IDs were not surfaced by the fuzzy-search API despite exhaustive prefix sweeps

---

## Namespace summary

| Namespace | Count |
|-----------|------:|
| aide | 2 |
| bacnet | 44 |
| cloudconnections | 99 |
| codesys3 | 7 |
| display | 8 |
| docker | 2 |
| drm | 6 |
| firmwareimage | 1 |
| firmwareupdate | 5 |
| frontled | 1 |
| ftp | 2 |
| ftps | 2 |
| identity | 3 |
| integratedwebbrowser | 6 |
| ipsec | 8 |
| ledstates | 16 |
| localusers | 9 |
| memorycard | 3 |
| networking | 68 |
| ntpclient | 6 |
| oauth2server | 4 |
| openvpn | 7 |
| passwordmanagement | 1 |
| reboot | 1 |
| serialinterfaces | 6 |
| snmp | 10 |
| ssh | 5 |
| systems | 7 |
| systemtime | 3 |
| timezone | 24 |
| touchpanel | 1 |
| version | 3 |
| wagodeviceaccess | 2 |
| webbasedmanagement | 1 |
| webserver | 19 |
| **Total** | **392** |

---

## Full parameter ID list (alphabetical)

```
0-0-aide-enabled
0-0-aide-isrunning
0-0-bacnet-datalinks
0-0-bacnet-datalinks-1-communicationmode
0-0-bacnet-datalinks-1-enabled
0-0-bacnet-datalinks-1-interface
0-0-bacnet-datalinks-1-networknumber
0-0-bacnet-datalinks-1-port
0-0-bacnet-datalinks-1-sc-allowanycertificates
0-0-bacnet-datalinks-1-sc-allowexpiredcertificates
0-0-bacnet-datalinks-1-sc-allowselfsignedcertificates
0-0-bacnet-datalinks-1-sc-certificateauthorityfile
0-0-bacnet-datalinks-1-sc-certificateauthorityfiledescription
0-0-bacnet-datalinks-1-sc-certificatefile
0-0-bacnet-datalinks-1-sc-certificatefiledescription
0-0-bacnet-datalinks-1-sc-connectioninfo
0-0-bacnet-datalinks-1-sc-csrfile
0-0-bacnet-datalinks-1-sc-failoverhuburi
0-0-bacnet-datalinks-1-sc-mode
0-0-bacnet-datalinks-1-sc-primaryhuburi
0-0-bacnet-datalinks-2-communicationmode
0-0-bacnet-datalinks-2-enabled
0-0-bacnet-datalinks-2-interface
0-0-bacnet-datalinks-2-networknumber
0-0-bacnet-datalinks-2-port
0-0-bacnet-datalinks-2-sc-allowanycertificates
0-0-bacnet-datalinks-2-sc-allowexpiredcertificates
0-0-bacnet-datalinks-2-sc-allowselfsignedcertificates
0-0-bacnet-datalinks-2-sc-certificateauthorityfile
0-0-bacnet-datalinks-2-sc-certificateauthorityfiledescription
0-0-bacnet-datalinks-2-sc-certificatefile
0-0-bacnet-datalinks-2-sc-certificatefiledescription
0-0-bacnet-datalinks-2-sc-connectioninfo
0-0-bacnet-datalinks-2-sc-csrfile
0-0-bacnet-datalinks-2-sc-failoverhuburi
0-0-bacnet-datalinks-2-sc-mode
0-0-bacnet-datalinks-2-sc-primaryhuburi
0-0-bacnet-general-broadcastiamanswer
0-0-bacnet-general-enabled
0-0-bacnet-general-overridexml
0-0-bacnet-general-overridexmldescription
0-0-bacnet-general-status
0-0-bacnet-general-storagelocation-eventlog
0-0-bacnet-general-storagelocation-persistence
0-0-bacnet-general-storagelocation-trendlog
0-0-bacnet-hotreload-enabled
0-0-cloudconnections
0-0-cloudconnections-1-cloudtype
0-0-cloudconnections-1-enabled
0-0-cloudconnections-1-identification-clientid
0-0-cloudconnections-1-messaging-cachemode
0-0-cloudconnections-1-messaging-compression
0-0-cloudconnections-1-messaging-messagingprotocol
0-0-cloudconnections-1-messaging-wagoprotocol-messageproperty
0-0-cloudconnections-1-messaging-wagoprotocol-senddeviceinfo
0-0-cloudconnections-1-messaging-wagoprotocol-senddevicestatus
0-0-cloudconnections-1-messaging-wagoprotocol-standardcommandsenabled
0-0-cloudconnections-1-status-connected
0-0-cloudconnections-1-status-dataprotocollive
0-0-cloudconnections-1-status-errorinformation
0-0-cloudconnections-1-status-filllevel
0-0-cloudconnections-1-status-isactive
0-0-cloudconnections-1-status-nativemqtt-countofmessages
0-0-cloudconnections-1-status-outgoingdatablocks
0-0-cloudconnections-1-status-wagoprotocol-collectionscountfromplc
0-0-cloudconnections-1-status-wagoprotocol-telemetrydatatransmission
0-0-cloudconnections-1-status-wagoprotocol-wagoprotocolversion
0-0-cloudconnections-1-status-warninginformation
0-0-cloudconnections-1-transport-authentication-authenticationmethod
0-0-cloudconnections-1-transport-authentication-cacertificate
0-0-cloudconnections-1-transport-authentication-cacertificatedescription
0-0-cloudconnections-1-transport-authentication-cacertificatemode
0-0-cloudconnections-1-transport-authentication-clientcertificate
0-0-cloudconnections-1-transport-authentication-clientcertificatedescription
0-0-cloudconnections-1-transport-authentication-devicekey
0-0-cloudconnections-1-transport-authentication-idscope
0-0-cloudconnections-1-transport-authentication-password
0-0-cloudconnections-1-transport-authentication-privatekey
0-0-cloudconnections-1-transport-authentication-privatekeydescription
0-0-cloudconnections-1-transport-authentication-registrationid
0-0-cloudconnections-1-transport-authentication-user
0-0-cloudconnections-1-transport-host
0-0-cloudconnections-1-transport-httpproxy-host
0-0-cloudconnections-1-transport-httpproxy-password
0-0-cloudconnections-1-transport-httpproxy-port
0-0-cloudconnections-1-transport-httpproxy-user
0-0-cloudconnections-1-transport-mqtt-cleansession
0-0-cloudconnections-1-transport-mqtt-lastwill-enabled
0-0-cloudconnections-1-transport-mqtt-lastwill-payload
0-0-cloudconnections-1-transport-mqtt-lastwill-qos
0-0-cloudconnections-1-transport-mqtt-lastwill-retain
0-0-cloudconnections-1-transport-mqtt-lastwill-topic
0-0-cloudconnections-1-transport-port
0-0-cloudconnections-1-transport-proxytype
0-0-cloudconnections-1-transport-transportprotocol
0-0-cloudconnections-1-transport-usetls
0-0-cloudconnections-2-cloudtype
0-0-cloudconnections-2-enabled
0-0-cloudconnections-2-identification-clientid
0-0-cloudconnections-2-messaging-cachemode
0-0-cloudconnections-2-messaging-compression
0-0-cloudconnections-2-messaging-messagingprotocol
0-0-cloudconnections-2-messaging-wagoprotocol-messageproperty
0-0-cloudconnections-2-messaging-wagoprotocol-senddeviceinfo
0-0-cloudconnections-2-messaging-wagoprotocol-senddevicestatus
0-0-cloudconnections-2-messaging-wagoprotocol-standardcommandsenabled
0-0-cloudconnections-2-status-connected
0-0-cloudconnections-2-status-dataprotocollive
0-0-cloudconnections-2-status-errorinformation
0-0-cloudconnections-2-status-filllevel
0-0-cloudconnections-2-status-isactive
0-0-cloudconnections-2-status-nativemqtt-countofmessages
0-0-cloudconnections-2-status-outgoingdatablocks
0-0-cloudconnections-2-status-wagoprotocol-collectionscountfromplc
0-0-cloudconnections-2-status-wagoprotocol-telemetrydatatransmission
0-0-cloudconnections-2-status-wagoprotocol-wagoprotocolversion
0-0-cloudconnections-2-status-warninginformation
0-0-cloudconnections-2-transport-authentication-authenticationmethod
0-0-cloudconnections-2-transport-authentication-cacertificate
0-0-cloudconnections-2-transport-authentication-cacertificatedescription
0-0-cloudconnections-2-transport-authentication-cacertificatemode
0-0-cloudconnections-2-transport-authentication-clientcertificate
0-0-cloudconnections-2-transport-authentication-clientcertificatedescription
0-0-cloudconnections-2-transport-authentication-devicekey
0-0-cloudconnections-2-transport-authentication-idscope
0-0-cloudconnections-2-transport-authentication-password
0-0-cloudconnections-2-transport-authentication-privatekey
0-0-cloudconnections-2-transport-authentication-privatekeydescription
0-0-cloudconnections-2-transport-authentication-registrationid
0-0-cloudconnections-2-transport-authentication-user
0-0-cloudconnections-2-transport-host
0-0-cloudconnections-2-transport-httpproxy-host
0-0-cloudconnections-2-transport-httpproxy-password
0-0-cloudconnections-2-transport-httpproxy-port
0-0-cloudconnections-2-transport-httpproxy-user
0-0-cloudconnections-2-transport-mqtt-cleansession
0-0-cloudconnections-2-transport-mqtt-lastwill-enabled
0-0-cloudconnections-2-transport-mqtt-lastwill-payload
0-0-cloudconnections-2-transport-mqtt-lastwill-qos
0-0-cloudconnections-2-transport-mqtt-lastwill-retain
0-0-cloudconnections-2-transport-mqtt-lastwill-topic
0-0-cloudconnections-2-transport-port
0-0-cloudconnections-2-transport-proxytype
0-0-cloudconnections-2-transport-transportprotocol
0-0-cloudconnections-2-transport-usetls
0-0-codesys3-applications
0-0-codesys3-deviceversion
0-0-codesys3-enabled
0-0-codesys3-homedirectory
0-0-codesys3-userauthentication-enabled
0-0-codesys3-webserver-enabled
0-0-codesys3-webserver-userauthentication-enabled
0-0-display-orientation
0-0-display-resolution
0-0-display-screencare-enabled
0-0-display-screencare-time
0-0-display-screensaver-enabled
0-0-display-screensaver-idletime
0-0-display-screensaver-setting
0-0-display-screensaver-text
0-0-docker-enabled
0-0-docker-isrunning
0-0-drm-deviceid
0-0-drm-evaluationtime
0-0-drm-license-encrypted-device
0-0-drm-license-shortened
0-0-drm-maximumlicenses
0-0-drm-status
0-0-firmwareimage-bootmedium
0-0-firmwareupdate-debuginfo
0-0-firmwareupdate-errorcause
0-0-firmwareupdate-progress
0-0-firmwareupdate-revertable
0-0-firmwareupdate-status
0-0-frontled-enabled
0-0-ftp-enabled
0-0-ftp-isrunning
0-0-ftps-enabled
0-0-ftps-isrunning
0-0-identity-description
0-0-identity-ordernumber
0-0-identity-serialnumber
0-0-integratedwebbrowser-favorites
0-0-integratedwebbrowser-monitoring-reconnect
0-0-integratedwebbrowser-monitoring-reconnectinterval
0-0-integratedwebbrowser-security-allowunverifiedcertificates
0-0-integratedwebbrowser-startpage
0-0-integratedwebbrowser-startpagefavorite
0-0-ipsec-certificate
0-0-ipsec-certificatedescription
0-0-ipsec-configfile
0-0-ipsec-configurationdescription
0-0-ipsec-enabled
0-0-ipsec-isrunning
0-0-ipsec-privatekey
0-0-ipsec-secretsfile
0-0-ledstates
0-0-ledstates-1-colors
0-0-ledstates-1-diagnosticinformation
0-0-ledstates-1-name
0-0-ledstates-2-colors
0-0-ledstates-2-diagnosticinformation
0-0-ledstates-2-name
0-0-ledstates-3-colors
0-0-ledstates-3-diagnosticinformation
0-0-ledstates-3-name
0-0-ledstates-4-colors
0-0-ledstates-4-diagnosticinformation
0-0-ledstates-4-name
0-0-ledstates-5-colors
0-0-ledstates-5-diagnosticinformation
0-0-ledstates-5-name
0-0-localusers
0-0-localusers-1-ispasswordexpired
0-0-localusers-1-name
0-0-localusers-13-ispasswordexpired
0-0-localusers-13-name
0-0-localusers-1001-ispasswordexpired
0-0-localusers-1001-name
0-0-localusers-1003-ispasswordexpired
0-0-localusers-1003-name
0-0-memorycard-isavailable
0-0-memorycard-iswriteprotected
0-0-memorycard-volumename
0-0-networking-bridges
0-0-networking-bridges-1-connectedethernetports
0-0-networking-bridges-1-ipconfiguration-addresses
0-0-networking-bridges-1-ipconfiguration-currentaddresses
0-0-networking-bridges-1-ipconfiguration-currentdefaultgateway
0-0-networking-bridges-1-ipconfiguration-sources
0-0-networking-bridges-1-ipconfiguration-staticdefaultgateway
0-0-networking-bridges-1-label
0-0-networking-bridges-1-macaddress
0-0-networking-bridges-1-name
0-0-networking-bridges-2-connectedethernetports
0-0-networking-bridges-2-ipconfiguration-addresses
0-0-networking-bridges-2-ipconfiguration-currentaddresses
0-0-networking-bridges-2-ipconfiguration-currentdefaultgateway
0-0-networking-bridges-2-ipconfiguration-sources
0-0-networking-bridges-2-ipconfiguration-staticdefaultgateway
0-0-networking-bridges-2-label
0-0-networking-bridges-2-macaddress
0-0-networking-bridges-2-name
0-0-networking-dns-customdnsservers
0-0-networking-dns-utilizeddnsservers
0-0-networking-domain-currentdomain
0-0-networking-domain-customdomain
0-0-networking-dummyinterfaces
0-0-networking-ethernetports
0-0-networking-ethernetports-1-broadcastprotection-enabled
0-0-networking-ethernetports-1-currentspeedduplex
0-0-networking-ethernetports-1-enabled
0-0-networking-ethernetports-1-haslink
0-0-networking-ethernetports-1-macaddress
0-0-networking-ethernetports-1-maclearning
0-0-networking-ethernetports-1-multicastprotection-enabled
0-0-networking-ethernetports-1-name
0-0-networking-ethernetports-1-speedduplex
0-0-networking-ethernetports-2-broadcastprotection-enabled
0-0-networking-ethernetports-2-currentspeedduplex
0-0-networking-ethernetports-2-enabled
0-0-networking-ethernetports-2-haslink
0-0-networking-ethernetports-2-macaddress
0-0-networking-ethernetports-2-maclearning
0-0-networking-ethernetports-2-multicastprotection-enabled
0-0-networking-ethernetports-2-name
0-0-networking-ethernetports-2-speedduplex
0-0-networking-hostname-currentname
0-0-networking-hostname-customname
0-0-networking-ipv4dipswitch
0-0-networking-portmirroring-destination
0-0-networking-portmirroring-enabled
0-0-networking-portmirroring-source
0-0-networking-routing-currentroutes
0-0-networking-routing-currentroutes-1-address
0-0-networking-routing-currentroutes-1-gatewayaddress
0-0-networking-routing-currentroutes-1-gatewaymetric
0-0-networking-routing-currentroutes-1-interface
0-0-networking-routing-currentroutes-1-source
0-0-networking-routing-customroutes
0-0-networking-routing-customroutes-1-address
0-0-networking-routing-customroutes-1-enabled
0-0-networking-routing-customroutes-1-gatewayaddress
0-0-networking-routing-customroutes-1-gatewaymetric
0-0-networking-routing-customroutes-1-interface
0-0-networking-routing-ipforwarding-enabled
0-0-networking-routing-ipmasqueradingrules
0-0-networking-routing-portforwardingrules
0-0-networking-stormprotection-broadcastratelimit
0-0-networking-stormprotection-multicastprotection-enabled
0-0-networking-stormprotection-multicastratelimit
0-0-networking-vlaninterfaces
0-0-ntpclient-configuredtimeservers
0-0-ntpclient-dynamicallyassignedtimeservers
0-0-ntpclient-enabled
0-0-ntpclient-isrunning
0-0-ntpclient-istimeserveravailable
0-0-ntpclient-updateinterval
0-0-oauth2server-accesstokenlifetime
0-0-oauth2server-authcodelifetime
0-0-oauth2server-refreshtokenlifetime
0-0-oauth2server-silentmodeenabled
0-0-openvpn-certificate
0-0-openvpn-certificatedescription
0-0-openvpn-configfile
0-0-openvpn-configurationdescription
0-0-openvpn-enabled
0-0-openvpn-isrunning
0-0-openvpn-privatekey
0-0-passwordmanagement-passworddata
0-0-reboot-status
0-0-serialinterfaces
0-0-serialinterfaces-1-assignedmode
0-0-serialinterfaces-1-assignedowner
0-0-serialinterfaces-1-currentmode
0-0-serialinterfaces-1-currentowner
0-0-serialinterfaces-1-name
0-0-snmp-communities
0-0-snmp-contact
0-0-snmp-description
0-0-snmp-enable
0-0-snmp-location
0-0-snmp-name
0-0-snmp-objectid
0-0-snmp-trapreceiversv1v2c
0-0-snmp-trapreceiversv3
0-0-snmp-users
0-0-ssh-enabled
0-0-ssh-ispasswordloginallowed
0-0-ssh-isrootloginallowed
0-0-ssh-isrunning
0-0-ssh-port
0-0-systems
0-0-systems-1-active
0-0-systems-1-available
0-0-systems-1-configured
0-0-systems-2-active
0-0-systems-2-available
0-0-systems-2-configured
0-0-systemtime-local-now
0-0-systemtime-now
0-0-systemtime-timezone
0-0-timezone
0-0-timezone-1-description
0-0-timezone-1-name
0-0-timezone-1-tzstring
0-0-timezone-2-description
0-0-timezone-2-name
0-0-timezone-3-description
0-0-timezone-3-name
0-0-timezone-4-description
0-0-timezone-4-name
0-0-timezone-5-description
0-0-timezone-5-name
0-0-timezone-6-description
0-0-timezone-6-name
0-0-timezone-7-description
0-0-timezone-7-name
0-0-timezone-8-description
0-0-timezone-8-name
0-0-timezone-9-description
0-0-timezone-9-name
0-0-timezone-10-description
0-0-timezone-10-name
0-0-timezone-11-description
0-0-timezone-11-name
0-0-touchpanel-acousticfeedback-enabled
0-0-version-firmwareversion
0-0-version-hardwarereleaseindex
0-0-version-softwarereleaseindex
0-0-wagodeviceaccess-allowedunauthenticatedrequests
0-0-wagodeviceaccess-corspolicy
0-0-webbasedmanagement-enabled
0-0-webserver-applications
0-0-webserver-applications-1-name
0-0-webserver-applications-2-httpport
0-0-webserver-applications-2-httpsport
0-0-webserver-applications-2-name
0-0-webserver-applications-2-useseparatedports
0-0-webserver-corspolicies
0-0-webserver-corspolicies-1-maxage
0-0-webserver-corspolicies-1-name
0-0-webserver-corspolicies-2-maxage
0-0-webserver-corspolicies-2-name
0-0-webserver-corspolicies-3-allowedorigins
0-0-webserver-corspolicies-3-maxage
0-0-webserver-corspolicies-3-name
0-0-webserver-defaultapplication
0-0-webserver-httpport
0-0-webserver-httpsport
0-0-webserver-protocols
0-0-webserver-tlsmode
```

---

## Notes

- **2 unresolved IDs:** exhaustive single-letter prefix queries (`0-0-a` through `0-0-w`) all returned `truncated: false` and sum to 392. The remaining 2 are not surfaceable via `find_parameters` fuzzy search — likely ranked below the result window for every query tried. Re-record via a raw `GET /wda/parameters?page[limit]=500` cassette during the first L3 run to capture them.
- **Edge-only namespaces** (not present on CC100/PFC): `bacnet`, `cloudconnections`, `display`, `docker`, `drm`, `frontled`, `integratedwebbrowser`, `ipsec`, `oauth2server`, `openvpn`, `touchpanel`, `webbasedmanagement`
- **List-type parameters** (header + numbered sub-items): `bacnet-datalinks`, `cloudconnections`, `ledstates`, `localusers`, `networking-bridges`, `networking-ethernetports`, `networking-routing-currentroutes`, `networking-routing-customroutes`, `serialinterfaces`, `snmp-communities`, `snmp-trapreceiversv1v2c`, `snmp-trapreceiversv3`, `snmp-users`, `timezone`, `webserver-applications`, `webserver-corspolicies`
- **Confirm firmware version** live: `GET /wda/parameters/0-0-version-firmwareversion` — this document assumes FW build 31 based on `devices.yaml` hint; the cassette stale-guard (CT-07) will enforce re-record if the build index has changed.
