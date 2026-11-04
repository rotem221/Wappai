import CoreBluetooth
import SwiftUI
import Security

final class WappaiBluetooth:NSObject,ObservableObject,CBCentralManagerDelegate,CBPeripheralDelegate {
    static let service=CBUUID(string:"57415050-4149-4000-8000-000000000001")
    private let rxID=CBUUID(string:"57415050-4149-4000-8000-000000000002")
    private let txID=CBUUID(string:"57415050-4149-4000-8000-000000000003")
    @Published var nearby:[CBPeripheral]=[]
    @Published var status=""
    @Published var paired=false
    @Published private(set) var rememberedDevice=UserDefaults.standard.string(forKey:"wappai.ble.device")
    var hasRememberedDevice:Bool {rememberedDevice != nil}
    @Published private(set) var setupRequested=false
    @Published private(set) var setupComplete=false
    private var foreground=true
    private var reconnect:DispatchWorkItem?
    @Published var networks:[Network]=[]
    @Published var scanning=false
    @Published var joining=false
    @Published var wifiConnected=false
    @Published private(set) var wifiStatusKnown=false
    private var monitorTimer:Timer?
    @Published var hardware:WappaiHardware = .round175c
    private var joiningSSID=""
    private var joinDeadline=Date.distantPast
    private var statusTimer:Timer?
    private var scanID=UUID()
    struct Network:Identifiable {var id:String{ssid};let ssid:String;let rssi:Int;let open:Bool}
    private var central:CBCentralManager!
    private var device:CBPeripheral?
    private var rx:CBCharacteristic?
    private var tx:CBCharacteristic?
    override init(){super.init();central=CBCentralManager(delegate:self,queue:.main)}
    func centralManagerDidUpdateState(_ central:CBCentralManager){if central.state == .poweredOn {scan()}else{paired=false;wifiStatusKnown=false;monitorTimer?.invalidate();monitorTimer=nil;status="יש להפעיל Bluetooth ולאפשר גישה בהגדרות"}}
    func scan(){foreground=true;guard central.state == .poweredOn else{return}
        if let id=rememberedDevice.flatMap(UUID.init(uuidString:)),let known=central.retrievePeripherals(withIdentifiers:[id]).first {
            if known.state == .connected {
                device=known;known.delegate=self
                if rx == nil || tx == nil {known.discoverServices([Self.service])}
                else if let tx,!tx.isNotifying {known.setNotifyValue(true,for:tx)}
                else if !paired,let tx {known.readValue(for:tx)}
                else {startStatusMonitoring();if setupRequested && !scanning {scanNetworks()}}
                return
            }
            if known.state == .disconnected {connect(known,automatic:true)}
            if known.state == .connected || known.state == .connecting {return}
        }
        central.scanForPeripherals(withServices:[Self.service],options:[CBCentralManagerScanOptionAllowDuplicatesKey:false])}
    func stopScan(){foreground=false;reconnect?.cancel();central.stopScan();monitorTimer?.invalidate();monitorTimer=nil;wifiStatusKnown=false}
    func centralManager(_ central:CBCentralManager,didDiscover peripheral:CBPeripheral,advertisementData:[String:Any],rssi RSSI:NSNumber){
        // Migrate owners paired before UUID persistence was introduced. A stored key
        // is only a candidate: the device must still authenticate it in `paired`.
        let known=peripheral.identifier.uuidString==rememberedDevice || SecureStore.get("ble.owner."+peripheral.identifier.uuidString) != nil
        if known && peripheral.state == .disconnected {connect(peripheral,automatic:true)}
        else if !nearby.contains(where:{$0.identifier==peripheral.identifier}) {nearby.append(peripheral)}
    }
    func connect(_ p:CBPeripheral,automatic:Bool=false){
        guard p.state != .connecting else{return}
        // An automatic transport reconnect must preserve the user's explicit
        // request to open Wi-Fi settings and scan after authentication.
        setupRequested = setupRequested || !automatic || joining;device=p;p.delegate=self
        status="מתחבר למכשיר…";central.connect(p);central.stopScan()
    }
    func endSetup(){if !joining {setupRequested=false;setupComplete=false}}
    private func startStatusMonitoring(){
        monitorTimer?.invalidate();guard foreground,paired else{return}
        write(["op":"status"])
        monitorTimer=Timer.scheduledTimer(withTimeInterval:20,repeats:true){[weak self] _ in
            guard let self,self.foreground,self.paired,!self.joining,!self.scanning else{return}
            self.write(["op":"status"])
        }
    }
    func beginSetup(){setupRequested=true;setupComplete=false;if paired{scanNetworks()}else{scan()}}
    private func scheduleReconnect(){
        reconnect?.cancel();guard foreground else{return}
        let work=DispatchWorkItem{[weak self] in self?.scan()};reconnect=work
        DispatchQueue.main.asyncAfter(deadline:.now()+4,execute:work)
    }
    func centralManager(_ central:CBCentralManager,didConnect peripheral:CBPeripheral){peripheral.discoverServices([Self.service])}
    func centralManager(_ central:CBCentralManager,didFailToConnect peripheral:CBPeripheral,error:Error?){status=error?.localizedDescription ?? "לא ניתן להתחבר";scheduleReconnect()}
    func centralManager(_ central:CBCentralManager,didDisconnectPeripheral peripheral:CBPeripheral,error:Error?){paired=false;wifiConnected=false;wifiStatusKnown=false;monitorTimer?.invalidate();monitorTimer=nil;scanning=false;scanID=UUID();rx=nil;tx=nil;status=joining ? "בודק את החיבור לרשת…":"המכשיר התנתק. אפשר להתחבר שוב.";nearby.removeAll();scheduleReconnect()}
    func peripheral(_ peripheral:CBPeripheral,didDiscoverServices error:Error?){for s in peripheral.services ?? [] {peripheral.discoverCharacteristics([rxID,txID],for:s)}}
    func peripheral(_ peripheral:CBPeripheral,didDiscoverCharacteristicsFor service:CBService,error:Error?){
        for c in service.characteristics ?? [] {if c.uuid==rxID{rx=c};if c.uuid==txID{tx=c;peripheral.setNotifyValue(true,for:c)}}
        if tx != nil {status="מתחבר באופן מוצפן. ייתכן שיופיע אישור Bluetooth של iOS."}
    }
    func peripheral(_ peripheral:CBPeripheral,didUpdateNotificationStateFor characteristic:CBCharacteristic,error:Error?){
        if let error {status=error.localizedDescription;return}
        // Claim/scan responses are notifications. Subscribe before sending any
        // commands so the first pairing response cannot be lost.
        if characteristic.uuid==txID && characteristic.isNotifying {peripheral.readValue(for:characteristic)}
    }
    private func ownerKey()->String {
        let key="ble.owner."+(device?.identifier.uuidString ?? "")
        if let saved=SecureStore.get(key){return saved}
        var bytes=[UInt8](repeating:0,count:32);guard SecRandomCopyBytes(kSecRandomDefault,bytes.count,&bytes)==errSecSuccess else{return ""}
        let value=bytes.map{String(format:"%02x",$0)}.joined();SecureStore.put(key,value);return value
    }
    func write(_ d:[String:Any]){guard let device,let rx,let data=try? JSONSerialization.data(withJSONObject:d),data.count<=min(512,device.maximumWriteValueLength(for:.withResponse)) else{status="ההודעה גדולה מדי לחיבור Bluetooth";return};device.writeValue(data,for:rx,type:.withResponse)}
    func peripheral(_ peripheral:CBPeripheral,didWriteValueFor characteristic:CBCharacteristic,error:Error?){if let error {status=error.localizedDescription}}
    func peripheral(_ peripheral:CBPeripheral,didUpdateValueFor characteristic:CBCharacteristic,error:Error?){
        if let error {status=error.localizedDescription;return}
        guard let data=characteristic.value,let d=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],let type=d["type"] as? String else{return}
        switch type {
        case "hello":
            if let board=d["board"] as? String {hardware=board.contains("216") ? .square216:board.contains("18") ? .rectangle18:.round175c}
            write(["op":"claim","key":ownerKey()])
        case "confirm_on_device":status="לחץ BOOT במכשיר כדי לאשר את החיבור לאייפון"
        case "paired":
            paired=true;rememberedDevice=peripheral.identifier.uuidString
            UserDefaults.standard.set(rememberedDevice,forKey:"wappai.ble.device")
            status="המכשיר שויך בהצלחה";startStatusMonitoring()
            if setupRequested && !joining {scanNetworks()}
        case "owned":
            if rememberedDevice==peripheral.identifier.uuidString {rememberedDevice=nil;UserDefaults.standard.removeObject(forKey:"wappai.ble.device")}
            status="המכשיר שייך לאייפון אחר. נדרש אישור הבעלים."
        case "network":if let ssid=d["ssid"] as? String,!networks.contains(where:{$0.ssid==ssid}){networks.append(.init(ssid:ssid,rssi:d["rssi"] as? Int ?? -100,open:d["open"] as? Bool ?? false))}
        case "scan_complete":scanning=false;networks.sort{$0.rssi>$1.rssi};status=networks.isEmpty ? "לא נמצאו רשתות 2.4GHz. קרב את המכשיר לנתב ונסה שוב.":"בחר רשת Wi‑Fi"
        case "connecting":status="מתחבר לרשת ובודק שהחיבור הצליח…"
        case "wifi_status":
            wifiStatusKnown=true
            if d["connected"] as? Bool != true {wifiConnected=false}
            if PairingPolicy.acceptsWiFi(connected:d["connected"] as? Bool == true,ssid:d["ssid"] as? String,joining:joining,requestedSSID:joiningSSID) {
                let finishedJoin=joining
                joining=false;wifiConnected=true;status="מחובר ל־\(d["ssid"] as? String ?? joiningSSID)";statusTimer?.invalidate()
                if finishedJoin {setupRequested=false;setupComplete=true}
            } else if d["failed"] as? Bool == true {
                joining=false;wifiConnected=false;status=(d["error"] as? String).flatMap{$0.isEmpty ? nil:$0} ?? "החיבור לרשת נכשל. נסה שוב.";statusTimer?.invalidate()
            }
        case "expired","denied":status="השיוך לא אושר. התחבר מחדש."
        default:break
        }
    }
    func scanNetworks(){
        setupRequested=true;setupComplete=false
        guard paired,tx?.isNotifying==true else{scan();return}
        guard !scanning else{return}
        networks=[];scanning=true;scanID=UUID();let request=scanID;status="מחפש רשתות בקרבת המכשיר…";write(["op":"scan"])
        DispatchQueue.main.asyncAfter(deadline:.now()+35){[weak self] in guard let self,self.scanning,self.scanID==request else{return};self.scanning=false;self.status="הסריקה לא הושלמה. נסה לסרוק שוב."}
    }
    func join(ssid:String,password:String){
        joining=true;wifiConnected=false;joiningSSID=ssid;joinDeadline=Date().addingTimeInterval(70)
        statusTimer?.invalidate()
        statusTimer=Timer.scheduledTimer(withTimeInterval:2,repeats:true){[weak self] timer in
            guard let self else{timer.invalidate();return}
            if Date()>self.joinDeadline {self.joining=false;self.status="לא התקבל אישור חיבור מהמכשיר. התחבר שוב ובדוק את הרשת.";timer.invalidate()}
            else if self.paired {self.write(["op":"status"])}
        }
        write(["op":"wifi","ssid":ssid,"password":password])
    }
}
