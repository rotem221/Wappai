import Foundation

// Keeping discovery separate from ownership prevents reconnects and device reboots
// from being presented as invitations to pair a new device.
enum PairingPolicy {
    static func offerDiscovery(nearby:Int,dismissed:Bool,remembered:Bool,authenticated:Bool,online:Bool,foreground:Bool)->Bool {
        nearby>0 && !dismissed && !remembered && !authenticated && !online && foreground
    }
    static func offerNetworkRecovery(authenticated:Bool,statusKnown:Bool,wifiConnected:Bool,online:Bool,joining:Bool,foreground:Bool,alreadyOffered:Bool)->Bool {
        authenticated && statusKnown && !wifiConnected && !online && !joining && foreground && !alreadyOffered
    }
    static func acceptsWiFi(connected:Bool,ssid:String?,joining:Bool,requestedSSID:String)->Bool {
        connected && !(ssid ?? "").isEmpty && (!joining || ssid==requestedSSID)
    }
}
