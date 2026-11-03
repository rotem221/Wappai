import SwiftUI
import AVKit

struct MeetingItem:Codable,Identifiable {
    let id:String;let title:String;let started:String;let state:String;let minutes:Double;let has_audio:Bool;let has_summary:Bool;var seconds:Double?
}
struct MeetingCapacity:Codable {let remaining_seconds:Int;let used_bytes:Int64;let quota_bytes:Int64;let cloud_configured:Bool;let max_session_seconds:Int}
struct RecordingStorage:Codable {var sd_supported:Bool?;var sd_present:Bool?;var status:String?;var available_bytes:Int64?}
struct MeetingLibrarySnapshot:Codable {var device_storage:RecordingStorage?;let items:[MeetingItem];let capacity:MeetingCapacity;let recording:Bool}
struct MeetingDetail:Codable {let id:String;let state:String;var title:String?;var transcript:String?;var summary:String?;var seconds:Double?;var stop_reason:String?;var audio_parts:[String]?;var live:Bool?}

struct MeetingLibrary:View {
    @ObservedObject var client:WappaiClient
    @State private var snapshot:MeetingLibrarySnapshot?
    @State private var error=""
    @State private var consent=false
    @State private var working=false
    @State private var selected:MeetingItem?
    var body:some View {
        List {
            if let s=snapshot {
                Section("זמן ואחסון") {
                    LabeledContent("זמן הקלטה זמין משוער",value:"\(min(s.capacity.remaining_seconds,s.capacity.max_session_seconds)/60) דקות")
                    if let storage=s.device_storage {
                        LabeledContent("כרטיס זיכרון",value:storage.status=="no_slot" ? "אין חריץ בדגם הזה":storage.sd_present==true ? "כרטיס זוהה":storage.sd_supported==true ? "לא נמצא כרטיס קריא":"לא דווח")
                        if let free=storage.available_bytes,storage.sd_present==true {LabeledContent("פנוי בכרטיס",value:ByteCountFormatter.string(fromByteCount:free,countStyle:.file))}
                    }
                    ProgressView(value:Double(s.capacity.used_bytes),total:Double(max(1,s.capacity.quota_bytes)))
                    Text(s.capacity.cloud_configured ? "ארכיון ענן מוגדר. העלאות שנכשלות נשמרות בשרת לניסיון חוזר.":"ההקלטות נשמרות בשרת שלך. ארכיון ענן אינו מוגדר.").font(.caption).foregroundStyle(.secondary)
                    Text("במכשיר ללא כרטיס, ניתוק רשת מוגבל לזיכרון הזמני. הקלטה עשויה להיעצר אם הזיכרון מתמלא; זמן הסוללה עשוי לקצר את משך ההקלטה.").font(.caption).foregroundStyle(.secondary)
                }
                Section {
                    if s.recording {Label("הקלטה פעילה במכשיר",systemImage:"record.circle").foregroundStyle(.red)
                        if let active=s.items.first(where:{$0.state=="recording"}) {let elapsed=Int(active.seconds ?? active.minutes*60);LabeledContent("משך ההקלטה",value:String(format:"%02d:%02d / %d דקות",elapsed/60,elapsed%60,min(s.capacity.max_session_seconds,s.capacity.remaining_seconds+elapsed)/60)).monospacedDigit()}
                        Button("סיום הקלטה",role:.destructive){Task{await control("stop")}}}
                    else {Button{consent=true}label:{Label("הקלטת פגישה במכשיר",systemImage:"mic.badge.plus")}.disabled(!client.device.online)}
                }.disabled(working)
                Section("הפגישות שלך") {
                    if s.items.isEmpty {Text("הפגישות שתקליטו יופיעו כאן").foregroundStyle(.secondary)}
                    ForEach(s.items){item in NavigationLink {MeetingDetailView(client:client,item:item)} label:{VStack(alignment:.leading,spacing:5){Text(item.title).font(.headline);Text("\(item.started.prefix(16).replacingOccurrences(of:"T",with:" ")) · \(Int(item.minutes)) דקות · \(meetingState(item.state))").font(.caption).foregroundStyle(.secondary)}}}
                }
            } else if error.isEmpty {ProgressView()}
            if !error.isEmpty {Text(error).foregroundStyle(.orange)}
        }.navigationTitle("פגישות").refreshable{await load()}
         .task{while !Task.isCancelled {await load();do{try await Task.sleep(for:.seconds(5))}catch{return}}}
         .confirmationDialog("התחלת הקלטת פגישה",isPresented:$consent,titleVisibility:.visible){Button("המשתתפים מודעים — התחלת הקלטה"){Task{await control("start")}}}message:{Text("המיקרופון במכשיר יקליט. השמע יישמר בשרת שלך ובענן אם הגדרת אותו; התמלול יישלח ל־Claude Code שהוגדר בשרת לצורך סיכום. יש ליידע את המשתתפים ולקבל את הסכמתם כנדרש.")}
    }
    private func load() async {do{snapshot=try JSONDecoder().decode(MeetingLibrarySnapshot.self,from:await client.call("/v1/meetings"));error=""}catch{self.error=error.localizedDescription}}
    private func control(_ action:String) async {working=true;defer{working=false};do{try await client.call("/v1/meetings/"+action,body:["consent":true]);await load()}catch{self.error=error.localizedDescription}}
}
func meetingState(_ state:String)->String {
    ["recording":"מקליט", "processing":"מעבד", "transcribed":"תומלל", "done":"מוכן", "audio_only":"הקלטה ללא תמלול", "interrupted":"נקטע", "summary_unavailable":"הסיכום אינו זמין", "processing_failed":"העיבוד נכשל — ההקלטה נשמרה"][state] ?? state
}
struct MeetingDetailView:View {
    @ObservedObject var client:WappaiClient
    let item:MeetingItem
    @Environment(\.dismiss) private var dismiss
    @State private var detail:MeetingDetail?
    @State private var error=""
    @State private var confirmDelete=false
    @State private var player:AVPlayer?
    @State private var audioURL:URL?
    @State private var loadingAudio=false
    @State private var audioTask:Task<Void,Never>?
    var body:some View {
        List {
            if let d=detail {
                Section {Text(meetingState(d.state));if let seconds=d.seconds{Text("\(Int(seconds)/60) דקות מוקלטות")};if let reason=d.stop_reason,!reason.isEmpty {Label("ההקלטה נעצרה לפני הסיום: \(reason)",systemImage:"exclamationmark.triangle").foregroundStyle(.orange)}}
                if let parts=d.audio_parts,parts.count>1 {Section("מקטעי הקלטה שנשמרו") {Text("איחוד השמע לא הושלם. כל המקטעים זמינים בנפרד; ניתן לנסות לעבד שוב.").font(.caption)
                    ForEach(parts,id:\.self){part in Button(part){audioTask=Task{await play(part:part)}}.disabled(loadingAudio)}
                    if let player {VideoPlayer(player:player).frame(height:90)}
                }} else if item.has_audio {Section("הקלטה") {if let player {VideoPlayer(player:player).frame(height:90)}else{Button("טעינת ההקלטה"){audioTask=Task{await play()}}.disabled(loadingAudio);if loadingAudio{ProgressView()}}}}
                if ["audio_only","processing_failed","summary_unavailable","interrupted"].contains(d.state){Section{Button("ניסיון נוסף לתמלול ולסיכום"){Task{do{try await client.call("/v1/meetings/"+item.id+"/retry",body:[:]);dismiss()}catch{self.error=error.localizedDescription}}}}}
                Section("סיכום") {Text(d.summary?.isEmpty==false ? d.summary!:"הסיכום עדיין אינו זמין").textSelection(.enabled)}
                Section("תמלול") {Text(d.transcript?.isEmpty==false ? d.transcript!:"התמלול עדיין אינו זמין").textSelection(.enabled)}
                if d.live != true && d.state != "recording" && d.state != "processing" {Section{Button("מחיקת הפגישה וההקלטה",role:.destructive){confirmDelete=true}}}
            }
            if !error.isEmpty{Text(error).foregroundStyle(.orange)}
        }.navigationTitle(item.title)
         .task{do{detail=try JSONDecoder().decode(MeetingDetail.self,from:await client.call("/v1/meetings/"+item.id))}catch{self.error=error.localizedDescription}}
         .confirmationDialog("למחוק את הפגישה, התמלול וההקלטה גם מהארכיון?",isPresented:$confirmDelete,titleVisibility:.visible){Button("מחיקה",role:.destructive){Task{do{try await client.call("/v1/meetings/"+item.id+"/delete",body:[:]);dismiss()}catch{self.error=error.localizedDescription}}}}
         .onDisappear{audioTask?.cancel();player?.pause();player=nil;if let audioURL{try? FileManager.default.removeItem(at:audioURL)}}
    }
    private func play(part:String?=nil) async {
        loadingAudio=true;defer{loadingAudio=false}
        do {player?.pause();player=nil;if let audioURL{try? FileManager.default.removeItem(at:audioURL)};let url=try await client.downloadMeetingAudio(item.id,part:part);if Task.isCancelled{try? FileManager.default.removeItem(at:url);return};audioURL=url;player=AVPlayer(url:url);player?.play()}catch{self.error=error.localizedDescription}
    }
}
