import Foundation
// Regressions: ordinary restored Wi-Fi has no pending join; old AP success must
// not complete a new join; losing BLE while Wi-Fi works must not invite pairing.
assert(PairingPolicy.acceptsWiFi(connected:true,ssid:"Home",joining:false,requestedSSID:""))
assert(!PairingPolicy.acceptsWiFi(connected:true,ssid:"Old",joining:true,requestedSSID:"New"))
assert(PairingPolicy.acceptsWiFi(connected:true,ssid:"New",joining:true,requestedSSID:"New"))
assert(!PairingPolicy.acceptsWiFi(connected:false,ssid:"New",joining:true,requestedSSID:"New"))
assert(!PairingPolicy.acceptsWiFi(connected:true,ssid:nil,joining:false,requestedSSID:""))
for online in [true,false] {for remembered in [true,false] {for authenticated in [true,false] {
    let offered=PairingPolicy.offerDiscovery(nearby:1,dismissed:false,remembered:remembered,authenticated:authenticated,online:online,foreground:true)
    assert(offered == (!online && !remembered && !authenticated))
}}}
assert(!PairingPolicy.offerDiscovery(nearby:1,dismissed:false,remembered:false,authenticated:false,online:false,foreground:false))
assert(!PairingPolicy.offerDiscovery(nearby:1,dismissed:true,remembered:false,authenticated:false,online:false,foreground:true))
assert(!PairingPolicy.offerDiscovery(nearby:0,dismissed:false,remembered:false,authenticated:false,online:false,foreground:true))
print("Pairing restoration, duplicate discovery and join acknowledgement regressions passed")
// A remembered/authenticated device needs Wi-Fi recovery, never new ownership.
assert(PairingPolicy.offerNetworkRecovery(authenticated:true,statusKnown:true,wifiConnected:false,online:false,joining:false,foreground:true,alreadyOffered:false))
for blocked in 0..<7 {
    assert(!PairingPolicy.offerNetworkRecovery(authenticated:blocked != 0,statusKnown:blocked != 1,wifiConnected:blocked == 2,online:blocked == 3,joining:blocked == 4,foreground:blocked != 5,alreadyOffered:blocked == 6))
}
print("Verified-offline recovery policy: unknown state, online devices, joining, background and repeat prompts suppressed")
