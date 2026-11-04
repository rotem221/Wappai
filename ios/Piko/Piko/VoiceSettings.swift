import SwiftUI
import AVFoundation

struct HomeBadge {let name:String;let on:Bool;let pending:Bool;let available:Bool}
struct VoiceAccount:Decodable {
    var provider:String;var style:String;var edge_voice:String;var voice_id:String;var model_id:String;var connected:Bool
    var user_address:String? = nil;var assistant_gender:String? = nil
}
struct ElevenVoice:Decodable,Identifiable {let id:String;let name:String;let description:String;let language:String}
struct ElevenModel:Decodable,Identifiable {let id:String;let name:String}
struct VoiceListing:Decodable {let voices:[ElevenVoice];let models:[ElevenModel];let next_cursor:String?}

struct VoiceSettings:View {
    @ObservedObject var client:WappaiClient
    @State private var account=VoiceAccount(provider:"edge",style:"lively",edge_voice:"he-IL-HilaNeural",voice_id:"",model_id:"eleven_v3",connected:false)
    @State private var voices:[ElevenVoice]=[]
    @State private var models:[ElevenModel]=[]
    @State private var cursor:String?
    @State private var search=""
    @State private var apiKey=""
    @State private var busy=false
    @State private var loaded=false
    @State private var error=""
    @State private var message=""
    @State private var player:AVAudioPlayer?
    var body:some View {
        Form {
            Section("לשון הפנייה") {
                Picker("איך לפנות אליי",selection:Binding(get:{account.user_address ?? "auto"},set:{account.user_address=$0})) {
                    Text("לשאול בשיחה").tag("auto");Text("זכר").tag("masculine");Text("נקבה").tag("feminine");Text("ניסוח ניטרלי").tag("neutral")
                }
                Picker("הדמות מדברת על עצמה",selection:Binding(get:{account.assistant_gender ?? "neutral"},set:{account.assistant_gender=$0})) {
                    Text("ניסוח ניטרלי").tag("neutral");Text("זכר").tag("masculine");Text("נקבה").tag("feminine")
                }
                Button("שמירת לשון הפנייה"){Task{await savePreferences()}}
                Text("אם לא נבחרה העדפה, Wappai ישאל בשיחה ויזכור את הבחירה. הקול אינו קובע את לשון הפנייה.").font(.caption).foregroundStyle(.secondary)
            }.disabled(busy || !loaded)
            Section("הקול של Wappai") {
                Picker("מקור הקול",selection:$account.provider){Text("קול מובנה").tag("edge");Text("ElevenLabs").tag("elevenlabs")}.accessibilityIdentifier("voiceProvider")
                Picker("אופי הדיבור",selection:$account.style){Text("חי ונלהב").tag("lively");Text("טבעי").tag("natural")}
                if account.provider=="edge" {
                    Picker("קול",selection:$account.edge_voice){Text("הילה").tag("he-IL-HilaNeural");Text("אברי").tag("he-IL-AvriNeural")}
                }
            }.disabled(busy || !loaded)
            if account.provider=="elevenlabs" {
                if !account.connected {
                    Section("חיבור ElevenLabs") {
                        SecureField("מפתח API",text:$apiKey).textInputAutocapitalization(.never).autocorrectionDisabled().environment(\.layoutDirection,.leftToRight)
                        Button("חיבור החשבון"){Task{await connect()}}.disabled(apiKey.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || busy)
                        Text("המפתח נשמר בשרת שלך בלבד. נדרשות הרשאות צפייה בקולות, במודלים ויצירת דיבור.").font(.caption).foregroundStyle(.secondary)
                    }
                } else {
                    Section("הקולות שלי") {
                        HStack{TextField("חיפוש קולות",text:$search).onSubmit{Task{await loadVoices()}};Button{Task{await loadVoices()}}label:{Image(systemName:"magnifyingglass")}.accessibilityLabel("חיפוש קולות")}.disabled(busy)
                        Picker("מודל בעברית",selection:$account.model_id){ForEach(models){Text($0.name).tag($0.id)}}.disabled(busy)
                        ForEach(voices){voice in
                            HStack {
                                Button{account.voice_id=voice.id;message=""}label:{HStack{Image(systemName:account.voice_id==voice.id ? "checkmark.circle.fill":"circle");VStack(alignment:.leading){Text(voice.name);if !voice.language.isEmpty{Text(voice.language).font(.caption).foregroundStyle(.secondary)}};Spacer()}}.buttonStyle(.plain)
                                Button{Task{await preview(voice)}}label:{Image(systemName:"play.circle")}.buttonStyle(.borderless).accessibilityLabel("האזנה ל־"+voice.name)
                            }.disabled(busy)
                        }
                        if voices.isEmpty && !busy{Text("לא נמצאו קולות. אפשר לשנות את החיפוש או להוסיף קול לחשבון ElevenLabs.").font(.caption).foregroundStyle(.secondary)}
                        if cursor != nil {Button("קולות נוספים"){Task{await loadVoices(more:true)}}.disabled(busy)}
                        Text("הדוגמה מושמעת באייפון. יצירת דיבור משתמשת במכסת חשבון ElevenLabs שלך.").font(.caption).foregroundStyle(.secondary)
                    }
                    Section {DisclosureGroup("עדכון מפתח החיבור") {
                        SecureField("מפתח API חדש",text:$apiKey).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Button("עדכון החיבור"){Task{await connect()}}.disabled(apiKey.isEmpty || busy)
                    }}
                }
            }
            Section {
                Button("שמירת הקול והסגנון"){Task{await save()}}.disabled(busy || !loaded || (account.provider=="elevenlabs" && (!account.connected || account.voice_id.isEmpty || models.isEmpty)))
                if busy {ProgressView("רגע…")}
                if !message.isEmpty {Text(message).foregroundStyle(.green)}
                if !error.isEmpty {Text(error).foregroundStyle(.orange)}
            }
        }.navigationTitle("קול ודיבור")
         .task{await load()}
         .onChange(of:account.provider){_,value in if value=="elevenlabs" && account.connected && voices.isEmpty {Task{await loadVoices()}}}
         .onDisappear{player?.stop()}
    }
    private func load() async {
        busy=true;defer{busy=false}
        do{account=try JSONDecoder().decode(VoiceAccount.self,from:await client.call("/v1/voice"));loaded=true;error=""}
        catch{self.error=error.localizedDescription}
        if account.provider=="elevenlabs" && account.connected{await loadVoices()}
    }
    private func accept(_ listing:VoiceListing,more:Bool=false){
        voices=more ? voices+listing.voices:listing.voices;models=listing.models;cursor=listing.next_cursor
        if !models.contains(where:{$0.id==account.model_id}),let model=models.first{account.model_id=model.id}
    }
    private func loadVoices(more:Bool=false) async {
        busy=true;defer{busy=false}
        do{accept(try JSONDecoder().decode(VoiceListing.self,from:await client.call("/v1/voice/search",body:["search":search,"cursor":more ? cursor ?? "":""])),more:more);error=""}
        catch{self.error=error.localizedDescription}
    }
    private func connect() async {
        busy=true;defer{busy=false}
        do{let data=try await client.call("/v1/voice/connect",body:["api_key":apiKey.trimmingCharacters(in:.whitespacesAndNewlines)]);accept(try JSONDecoder().decode(VoiceListing.self,from:data));account.connected=true;apiKey="";error="";message="החשבון מחובר. בחר קול ושמור."}
        catch{self.error=error.localizedDescription}
    }
    private func savePreferences() async {
        busy=true;defer{busy=false}
        do{account=try JSONDecoder().decode(VoiceAccount.self,from:await client.call("/v1/voice/preferences",body:["user_address":account.user_address ?? "auto","assistant_gender":account.assistant_gender ?? "neutral"]));error="";message="לשון הפנייה נשמרה"}
        catch{self.error=error.localizedDescription}
    }
    private func save() async {
        busy=true;defer{busy=false}
        do{account=try JSONDecoder().decode(VoiceAccount.self,from:await client.call("/v1/voice",body:["provider":account.provider,"style":account.style,"edge_voice":account.edge_voice,"voice_id":account.voice_id,"model_id":account.model_id]));error="";message="הקול והסגנון נשמרו";try? await client.refresh()}
        catch{self.error=error.localizedDescription}
    }
    private func preview(_ voice:ElevenVoice) async {
        busy=true;defer{busy=false};player?.stop()
        do{let data=try await client.call("/v1/voice/preview",body:["voice_id":voice.id,"model_id":account.model_id,"style":account.style],timeout:75)
            try AVAudioSession.sharedInstance().setCategory(.playback,mode:.spokenAudio);try AVAudioSession.sharedInstance().setActive(true)
            player=try AVAudioPlayer(data:data);player?.play();error=""
        }catch{self.error=error.localizedDescription}
    }
}
