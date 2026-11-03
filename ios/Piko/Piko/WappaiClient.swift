import SwiftUI
import Security

struct ChatSession: Codable, Identifiable { let id: String; var title: String; let provider: String; let created: Double }
struct ChatMessage: Codable, Identifiable { let id: String; let session_id: String; let role: String; var text: String; let created: Double }
struct PipSkin: Codable, Identifiable { let id: String; let name: String; let rig: Int; let color: Int; var asset_id:String?=nil; var description:String?=nil; var builtin:Bool {["pip","nori","orbit"].contains(id)} }
struct AgentOption: Codable, Identifiable { let id: String; let available: Bool }
struct DeviceStatus: Codable { var online: Bool; var fw_version: String?; var battery: Battery?; var rssi:Int?; var board:String?; var device_id:String?; struct Battery: Codable { var pct: Int?; var charging: Bool? } }
struct DeviceSettings:Codable {var brightness:Int?;var volume:Int?;var hold_to_talk:Bool?;var shake_reaction:Bool?;var character_sounds:Bool?;var reduced_motion:Bool?;var dim_seconds:Int?;var sleep_seconds:Int?;var tts_voice:String?;var live_transcription:Bool?}
struct Snapshot: Codable { let sessions: [ChatSession]; let active_session: String; let messages: [ChatMessage]; let cursor: Int; let device: DeviceStatus; let pips: [PipSkin]; let providers: [AgentOption];let settings:DeviceSettings;var selected_pip:String? }

enum SecureStore {
    static func get(_ key: String) -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,kSecAttrService as String:"com.dadon.wappai",kSecAttrAccount as String:key,kSecReturnData as String:true]
        var item: CFTypeRef?; guard SecItemCopyMatching(query as CFDictionary,&item)==errSecSuccess, let data=item as? Data else{return nil}
        return String(data:data,encoding:.utf8)
    }
    static func put(_ key:String,_ value:String) {
        let query: [String:Any]=[kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:"com.dadon.wappai",kSecAttrAccount as String:key]
        SecItemDelete(query as CFDictionary)
        var add=query; add[kSecValueData as String]=Data(value.utf8); add[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(add as CFDictionary,nil)
    }
}
@MainActor final class WappaiClient: ObservableObject {
    @Published var sessions:[ChatSession]=[]
    @Published var messages:[ChatMessage]=[]
    @Published var pips:[PipSkin]=[.init(id:"pip",name:"Pip",rig:0,color:0x80F2CD),.init(id:"nori",name:"Nori",rig:1,color:0xFFB18E),.init(id:"orbit",name:"Orbit",rig:2,color:0x8DC8FF)]
    @Published var preferences=DeviceSettings()
    @Published var providers:[AgentOption]=[]
    @Published var device=DeviceStatus(online:false)
    @Published var active=""
    @Published var state="idle"
    @Published var liveTranscript=""
    @Published var interaction=""
    @Published var homeBadge:HomeBadge?
    private var badgeExpiry:Task<Void,Never>?
    @Published var error=""
    @Published var connected=false
    @Published var paired=false
    @Published var chosenID=UserDefaults.standard.string(forKey:"wappai.pip.id") ?? "pip"
    @Published var art:[String:[UIImage]]=[:]
    private var loadingArt=Set<String>()
    var selectedSkin:PipSkin? {pips.first{$0.id==chosenID}}
    @Published var chosenPip=UserDefaults.standard.integer(forKey:"wappai.pip.rig")
    @Published var chosenColor=UserDefaults.standard.integer(forKey:"wappai.pip.color")
    @Published var server=UserDefaults.standard.string(forKey:"wappai.server") ?? ""
    private var socket:URLSessionWebSocketTask?
    private var loop:Task<Void,Never>?
    private var cursor=0
    private var token:String { SecureStore.get("hub.token."+server) ?? "" }
    var busy:Bool { ["thinking","working","speaking","listening"].contains(state) }
    var uiTesting:Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--qa-ui-fixture")
        #else
        return false
        #endif
    }
    init() {
        paired = !token.isEmpty
        if uiTesting {
            paired=true;connected=true;device=DeviceStatus(online:true,fw_version:"1.0.0-dev",battery:.init(pct:75,charging:false),rssi:-55,board:"ws-s3-175c")
            active="ui-qa";sessions=[.init(id:active,title:"בדיקת ממשק",provider:"codex",created:0)]
            messages=[.init(id:"qa-message",session_id:active,role:"assistant",text:"בדיקה מקומית ללא חיבור לשרת",created:0)]
            chosenID="pip";chosenPip=0;chosenColor=0
        }
    }
    private func url(_ path:String) throws -> URL {
        guard var base=URLComponents(string:server),base.scheme=="https",base.host != nil,base.user==nil,base.password==nil else { throw URLError(.badURL) }
        base.path=path; base.query=nil; base.fragment=nil
        guard let result=base.url else{throw URLError(.badURL)};return result
    }
    @discardableResult func call(_ path:String,body:[String:Any]?=nil,auth:Bool=true,timeout:TimeInterval=20) async throws -> Data {
        if uiTesting {
            if path=="/v1/meetings",body==nil{return Data(#"{"items":[{"id":"20261104-100000","title":"תכנון ההשקה","started":"2026-11-04T10:00:00","state":"done","minutes":24,"has_audio":false,"has_summary":true}],"capacity":{"remaining_seconds":7200,"used_bytes":850000000,"quota_bytes":4294967296,"cloud_configured":false,"max_session_seconds":18000},"recording":false}"#.utf8)}
            if path=="/v1/meetings/20261104-100000",body==nil{return Data(#"{"id":"20261104-100000","title":"תכנון ההשקה","state":"done","seconds":1440,"summary":"ההשקה מתוכננת ליום חמישי.\nדנה תסיים את בדיקת התקציב עד יום שני.","transcript":"[0:00:02] נתחיל בתכנון ההשקה.\n[0:00:08] דנה תבדוק את התקציב עד יום שני."}"#.utf8)}
            if path=="/v1/voice",body==nil{return Data(#"{"provider":"edge","style":"lively","edge_voice":"he-IL-HilaNeural","voice_id":"","model_id":"eleven_v3","connected":false}"#.utf8)}
            if path=="/v1/pip-jobs" && body==nil{return Data("[]".utf8)};throw URLError(.notConnectedToInternet)}
        var request=URLRequest(url:try url(path));request.timeoutInterval=timeout
        if auth {request.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")}
        if let body {request.httpMethod="POST";request.setValue("application/json",forHTTPHeaderField:"Content-Type");request.httpBody=try JSONSerialization.data(withJSONObject:body)}
        let (data,response)=try await URLSession.shared.data(for:request)
        guard let response=response as? HTTPURLResponse,(200..<300).contains(response.statusCode) else {
            let detail=(try? JSONSerialization.jsonObject(with:data) as? [String:Any])?["detail"] as? String
            throw NSError(domain:"Wappai",code:(response as? HTTPURLResponse)?.statusCode ?? 0,userInfo:[NSLocalizedDescriptionKey:detail ?? "לא ניתן להתחבר לשרת"])
        }
        return data
    }
    func downloadMeetingAudio(_ id:String, part:String?=nil) async throws -> URL {
        var components=URLComponents(url:try url("/v1/meetings/"+id+"/audio"),resolvingAgainstBaseURL:false)!
        if let part {components.queryItems=[URLQueryItem(name:"part",value:part)]}
        var request=URLRequest(url:components.url!);request.timeoutInterval=300
        request.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")
        let (file,response)=try await URLSession.shared.download(for:request)
        guard let http=response as? HTTPURLResponse,http.statusCode==200 else{throw URLError(.badServerResponse)}
        let suffix=response.mimeType=="audio/wav" ? "wav":"m4a"
        let target=FileManager.default.temporaryDirectory.appendingPathComponent("wappai-meeting-"+UUID().uuidString+"."+suffix)
        try FileManager.default.moveItem(at:file,to:target);return target
    }
    func pair(code:String) async {
        do {
            server=server.trimmingCharacters(in:.whitespacesAndNewlines).trimmingCharacters(in:CharacterSet(charactersIn:"/"))
            let data=try await call("/v1/pair",body:["code":code],auth:false)
            guard let obj=try JSONSerialization.jsonObject(with:data) as? [String:String],let key=obj["token"] else{return}
            SecureStore.put("hub.token."+server,key);UserDefaults.standard.set(server,forKey:"wappai.server");paired=true;error="";start()
        } catch {self.error=error.localizedDescription}
    }
    func refresh() async throws {
        let snap=try JSONDecoder().decode(Snapshot.self,from:await call("/v1/snapshot"))
        liveTranscript="";interaction="";homeBadge=nil
        sessions=snap.sessions;messages=snap.messages;active=snap.active_session;device=snap.device;pips=snap.pips;providers=snap.providers;preferences=snap.settings;cursor=snap.cursor
        if let id=snap.selected_pip,let p=pips.first(where:{$0.id==id}){choose(p)}
        for p in pips where p.asset_id != nil {await loadArt(p)}
    }
    func start() {
        guard paired && !uiTesting else{return}; stop()
        loop=Task {
            var delay=1
            while !Task.isCancelled {
                do {
                    try await refresh()
                    var components=URLComponents(url:try url("/v1/events"),resolvingAgainstBaseURL:false)!
                    components.scheme="wss";components.queryItems=[.init(name:"after",value:String(cursor))]
                    var request=URLRequest(url:components.url!);request.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")
                    let ws=URLSession.shared.webSocketTask(with:request);socket=ws;ws.resume();connected=true;error="";delay=1
                    while !Task.isCancelled {
                        let message=try await ws.receive()
                        let data:Data
                        switch message {case .data(let d):data=d;case .string(let s):data=Data(s.utf8);@unknown default:continue}
                        guard let obj=try JSONSerialization.jsonObject(with:data) as? [String:Any] else{continue}
                        let next=obj["cursor"] as? Int ?? cursor
                        if next<cursor {continue};cursor=next
                        let type=obj["type"] as? String ?? ""
                        if type=="session.active" {try await refresh();continue}
                        if let sid=obj["session_id"] as? String,sid != active {continue}
                        if type=="transcript.partial" {liveTranscript=preferences.live_transcription == true ? (obj["text"] as? String ?? ""):""}
                        if type=="interaction" {interaction=obj["text"] as? String ?? "";state="thinking";homeBadge=nil}
                        if type=="device.badge",let dev=obj["dev"] as? [String:Any] {
                            homeBadge=HomeBadge(name:dev["name"] as? String ?? "",on:dev["on"] as? Bool ?? false,pending:obj["pending"] as? Bool ?? false,available:dev["available"] as? Bool ?? false)
                            badgeExpiry?.cancel();let ttl=obj["ttl"] as? Int ?? 12
                            badgeExpiry=Task{try? await Task.sleep(for:.seconds(ttl));if !Task.isCancelled{homeBadge=nil}}
                        }
                        if type=="state" {state=obj["emotion"] as? String ?? "idle"}
                        if type=="stop" || type=="turn.completed" || type=="turn.failed" {state="idle";liveTranscript="";interaction="";if type != "turn.completed"{homeBadge=nil}}
                        if type=="heard" || type=="say" {
                            liveTranscript="";interaction="";
                            let id=obj["message_id"] as? String ?? UUID().uuidString
                            let text=obj["full_text"] as? String ?? obj["text"] as? String ?? ""
                            if let index=messages.firstIndex(where:{$0.id==id}) {messages[index].text=text}
                            else {messages.append(.init(id:id,session_id:active,role:type=="heard" ? "user":"assistant",text:text,created:Date().timeIntervalSince1970))}
                            if type=="say" {state="speaking"}
                        }
                        if type=="pips.updated" {try await refresh();continue}
                        if type=="pip.selected" {let id=obj["pip_id"] as? String ?? ["pip","nori","orbit"][min(2,max(0,obj["pip"] as? Int ?? 0))];if let p=pips.first(where:{$0.id==id}){choose(p);await loadArt(p)}}
                        if type=="heard",let index=sessions.firstIndex(where:{$0.id==active && $0.title=="שיחה חדשה"}) {sessions[index].title=String((obj["text"] as? String ?? "שיחה חדשה").prefix(60))}
                        if type=="device.connection" {device.online=obj["online"] as? Bool ?? false;if device.online {try? await refresh()}}
                        if type=="status" {device.online=true;device.rssi=obj["rssi"] as? Int; if let board=obj["board"] as? String {device.board=board}}
                        if type=="status",let battery=obj["battery"] as? [String:Any] { device.battery = .init(pct:battery["pct"] as? Int,charging:battery["charging"] as? Bool) }
                    }
                } catch {if !Task.isCancelled {self.error="החיבור נותק. מנסה להתחבר מחדש…"}}
                connected=false;socket?.cancel(with:.goingAway,reason:nil)
                try? await Task.sleep(for:.seconds(delay));delay=min(20,delay*2)
            }
        }
    }
    func stop(){loop?.cancel();loop=nil;socket?.cancel(with:.goingAway,reason:nil);socket=nil;connected=false}
    func send(_ text:String) async -> Bool {
        do {try await call("/v1/sessions/\(active)/messages",body:["text":text,"idempotency_key":UUID().uuidString]);state="thinking";error="";return true}
        catch {self.error=error.localizedDescription;return false}
    }
    func cancel() async {do {try await call("/v1/stop",body:[:]);state="idle"}catch{self.error=error.localizedDescription}}
    func newSession(_ provider:String="claude") async {
        do {try await call("/v1/sessions",body:["provider":provider]);try await refresh();state="idle"}catch{self.error=error.localizedDescription}
    }
    func select(_ sid:String) async {do{try await call("/v1/sessions/\(sid)/select",body:[:]);try await refresh()}catch{self.error=error.localizedDescription}}
    func choose(_ pip:PipSkin){chosenID=pip.id;chosenPip=pip.rig;chosenColor=pip.color;UserDefaults.standard.set(pip.id,forKey:"wappai.pip.id");UserDefaults.standard.set(pip.rig,forKey:"wappai.pip.rig");UserDefaults.standard.set(pip.color,forKey:"wappai.pip.color")}
    func activate(_ pip:PipSkin) async {do{try await call("/v1/pips/\(pip.id)/activate",body:[:],timeout:70);choose(pip);await loadArt(pip);error=""}catch{self.error=error.localizedDescription}}
    func loadArt(_ pip:PipSkin) async {
        guard let aid=pip.asset_id,art[aid]==nil,!loadingArt.contains(aid),aid.count==32,aid.allSatisfy({$0.isHexDigit}) else{return}
        loadingArt.insert(aid);defer{loadingArt.remove(aid)}
        do {
            let folder=FileManager.default.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("PipArt")
            try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
            let file=folder.appendingPathComponent(aid+".png")
            let data:Data
            if let cached=try? Data(contentsOf:file){data=cached}else{data=try await call("/v1/pip-assets/\(aid)/atlas.png");try data.write(to:file,options:.atomic)}
            guard let atlas=UIImage(data:data)?.cgImage,atlas.width==384,atlas.height==576 else{throw URLError(.cannotDecodeContentData)}
            art[aid]=(0..<24).compactMap{index in atlas.cropping(to:CGRect(x:index%4*96,y:index/4*96,width:96,height:96)).map{UIImage(cgImage:$0)}}
        }catch{self.error="לא ניתן לטעון את איורי הדמות. אפשר לנסות שוב בגלריה."}
    }
    func removePip(_ pip:PipSkin) async {guard !pip.builtin else{return};do{try await call("/v1/pips/\(pip.id)/delete",body:[:],timeout:80);try await refresh();error=""}catch{self.error=error.localizedDescription}}
    func setting(_ key:String,_ value:Any) async {do{try await call("/v1/settings",body:[key:value]);error=""}catch{self.error=error.localizedDescription}}
}
