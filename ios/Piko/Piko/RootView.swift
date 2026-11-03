import SwiftUI

struct RootView:View {
    @StateObject private var client=WappaiClient()
    @StateObject private var bluetooth=WappaiBluetooth()
    @StateObject private var firmwareUpdates=FirmwareUpdates()
    @Environment(\.scenePhase) private var phase
    @AppStorage("wappai.appearance") private var appearance="system"
    @AppStorage("wappai.characterSounds") private var characterSounds=true
    @AppStorage("wappai.pip.hidden") private var pipHidden=false
    @State private var draft=""
    @State private var showSettings=false
    @State private var showSessions=false
    @State private var showPips=false
    @State private var showPairing=false
    @State private var dismissedDiscovery=false
    @State private var previewHardware:WappaiHardware?
    @State private var studioPip:PipSkin?
    var body:some View {
        NavigationStack {
            VStack(spacing:0){
                if !client.paired {welcome}
                else {
                    ScrollViewReader {proxy in
                        ScrollView {
                            LazyVStack(spacing:17){
                                Text("Wappai · מקום קטן לכל מה שחשוב").font(.caption).foregroundStyle(.secondary).padding(.top,20)
                                if client.messages.isEmpty {
                                    Color.clear.frame(height:45)
                                    Text("אני כאן בשבילך").font(.title2.weight(.semibold))
                                    Text("אפשר לדבר דרך המכשיר או לכתוב כאן.").font(.subheadline).foregroundStyle(.secondary)
                                }
                                ForEach(client.messages){message in
                                    HStack(alignment:.bottom){
                                        if message.role=="user"{Spacer(minLength:45)}
                                        Text(message.text).font(.body).textSelection(.enabled)
                                            .padding(.horizontal,17).padding(.vertical,12)
                                            .foregroundStyle(message.role=="user" ? Color.white:Color.primary)
                                            .background(message.role=="user" ? Color.blue:Color(uiColor:.secondarySystemBackground),in:RoundedRectangle(cornerRadius:23))
                                            .environment(\.layoutDirection,.rightToLeft)
                                        if message.role != "user"{Spacer(minLength:45)}
                                    }.environment(\.layoutDirection,.leftToRight).id(message.id)
                                }
                                if !client.liveTranscript.isEmpty {
                                    HStack{Spacer(minLength:45);Text(client.liveTranscript).foregroundStyle(.secondary).padding(14).background(Color.blue.opacity(0.08),in:RoundedRectangle(cornerRadius:23))}.accessibilityLabel("תמלול חי: "+client.liveTranscript)
                                }
                                if let badge=client.homeBadge {HStack{Label(badge.name,systemImage:"power").font(.caption.weight(.medium));if badge.pending {ProgressView().controlSize(.mini)}}.foregroundStyle(badge.available && badge.on && !badge.pending ? Color.green:Color.secondary).padding(9).background(.thinMaterial,in:Capsule())}
                                if client.busy {HStack{ProgressView();Text(client.state=="listening" ? "מקשיב…":client.state=="speaking" ? "משיב…":client.interaction.isEmpty ? "חושב…":client.interaction).font(.caption).foregroundStyle(.secondary);Spacer()}.padding(.horizontal,12)}
                                Color.clear.frame(height:pipHidden ? 1:90).id("end")
                            }.padding(.horizontal,18).padding(.bottom,15)
                        }.scrollDismissesKeyboard(.interactively)
                         .onChange(of:client.liveTranscript){_,_ in proxy.scrollTo("end",anchor:.bottom)}
                         .onChange(of:client.messages.count){_,_ in withAnimation{proxy.scrollTo("end",anchor:.bottom)}}
                         .onChange(of:client.messages.last?.text){_,_ in proxy.scrollTo("end",anchor:.bottom)}
                    }
                    if !client.error.isEmpty {Text(client.error).font(.caption).foregroundStyle(.orange).padding(8).accessibilityIdentifier("connectionError")}
                }
            }
            .overlay {if client.paired {FloatingPip(client:client,paused:showSettings || showSessions || showPips || showPairing || studioPip != nil,open:{showPips=true})}}
            .background(Color(uiColor:.systemBackground))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement:.principal){
                    VStack(spacing:2){
                        Text(client.sessions.first(where:{$0.id==client.active})?.title ?? "Wappai")
                            .font(.headline).lineLimit(1).truncationMode(.tail)
                        Text(!client.connected && client.paired ? "מתחבר…":client.device.online ? "המכשיר מחובר":"המכשיר לא מחובר")
                            .font(.caption2).foregroundStyle(.secondary)
                    }.accessibilityElement(children:.combine)
                }
                ToolbarItem(placement:.topBarLeading){Button{withAnimation(.spring(response:0.36,dampingFraction:0.88)){showSessions=true}}label:{Image(systemName:"sidebar.leading")}.accessibilityLabel("השיחות שלי").disabled(!client.paired)}
                ToolbarItem(placement:.topBarTrailing){Button{showSettings=true}label:{Image(systemName:"gearshape")}.accessibilityLabel("הגדרות")}
            }
            .safeAreaInset(edge:.bottom,spacing:0){if client.paired {composer}}
            .sheet(isPresented:$showSettings){settings}
            .sheet(isPresented:$showPips){PipGallery(client:client)}
            .sheet(item:$studioPip){pip in ExpressionStudio(client:client,pip:pip)}
            .sheet(item:$previewHardware){hardware in NavigationStack{DeviceShowroom(hardware:hardware)}}
            .sheet(isPresented:$showPairing,onDismiss:{dismissedDiscovery=true}){PairingView(bluetooth:bluetooth).presentationDetents([.medium]).presentationDragIndicator(.visible)}
            .task(id:bluetooth.nearby.count){
                // Allow the existing hub session and remembered BLE owner to restore first.
                try? await Task.sleep(for:.seconds(2))
                guard !Task.isCancelled else{return}
                if PairingPolicy.offerDiscovery(nearby:bluetooth.nearby.count,dismissed:dismissedDiscovery,remembered:bluetooth.hasRememberedDevice,authenticated:bluetooth.paired,online:client.device.online,foreground:phase == .active){showPairing=true}
            }
            .onChange(of:bluetooth.wifiConnected){_,connected in if connected {showPairing=false}}
            .onChange(of:client.device.online){_,online in if online && !bluetooth.joining {showPairing=false}}
            .onChange(of:phase){_,value in if value == .active {client.start();bluetooth.scan();Task{if client.device.online{await firmwareUpdates.check(board:client.device.board,version:client.device.fw_version,fixture:client.uiTesting)}}}else{client.stop();bluetooth.stopScan()}}
            .task {
                let args=ProcessInfo.processInfo.arguments
                #if DEBUG
                if args.contains("--show-pairing"){showPairing=true}
                if args.contains("--show-pips"){showPips=true}
                if args.contains("--show-studio"){studioPip=client.pips.first}
                if args.contains("--show-settings"){showSettings=true}
                if args.contains("--show-sidebar"){showSessions=true}
                if let i=args.firstIndex(of:"--preview-model"),args.count>i+1{previewHardware=WappaiHardware(rawValue:args[i+1])}
                #endif
                if let index=args.firstIndex(of:"--pair-code"),args.count>index+1 {await client.pair(code:args[index+1])}
                else {client.start()}
            }
        }.tint(Color(rgb:0x258E73))
         .task(id:(client.device.board ?? "")+":"+(client.device.fw_version ?? "")+":"+String(client.device.online)) {
             if client.device.online {await firmwareUpdates.check(board:client.device.board,version:client.device.fw_version,fixture:client.uiTesting)}
         }
         .alert("עדכון קושחה זמין",isPresented:Binding(get:{firmwareUpdates.notice != nil},set:{if !$0{firmwareUpdates.notice=nil}})) {
             Button("פרטי העדכון"){firmwareUpdates.notice=nil;showSettings=true}
             Button("מאוחר יותר",role:.cancel){firmwareUpdates.notice=nil}
         } message:{Text("פורסמה גרסה חדשה שמתאימה לדגם שלכם. ניתן לבדוק את פרטי ההתקנה בהגדרות.")}
         .preferredColorScheme(appearance=="system" ? nil:appearance=="light" ? .light:.dark)
         .modifier(ConversationDrawer(client:client,visible:$showSessions))
         .onChange(of:client.state){_,state in
             if characterSounds && state != "speaking" && state != "listening" {PipSound.shared.play(rig:client.chosenPip,cue:PipExpression.named(state).cue)}
             else {PipSound.shared.stop()}
         }
    }
    private var composer:some View {
        HStack(alignment:.bottom,spacing:10){
            Button{showPips=true}label:{Image(systemName:"face.smiling").font(.title2).frame(width:44,height:44).wappaiGlass(radius:22)}.accessibilityLabel("הדמויות שלי")
            TextField("הודעה ל־Wappai",text:$draft,axis:.vertical).lineLimit(1...5).padding(.horizontal,14).padding(.vertical,11)
                .wappaiGlass(radius:25).accessibilityIdentifier("messageComposer")
            Button{
                if client.busy {Task{await client.cancel()}}
                else {let text=draft.trimmingCharacters(in:.whitespacesAndNewlines);guard !text.isEmpty else{return};Task{if await client.send(text){draft=""}}}
            }label:{Image(systemName:client.busy ? "stop.fill":"arrow.up").font(.system(size:17,weight:.bold)).foregroundStyle(.white).frame(width:42,height:42).background(client.connected && (client.busy || !draft.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty) ? Color.blue:Color(uiColor:.tertiarySystemFill),in:Circle())}
            .disabled(!client.connected || (!client.busy && draft.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty))
            .accessibilityLabel(client.busy ? "עצור תשובה":"שלח הודעה")
        }.padding(.horizontal,12).padding(.vertical,9)
    }
    private var welcome:some View {
        ScrollView{VStack(spacing:22){
            DeviceIllustration().padding(.top,35).padding(.bottom,15)
            Text("קטן בכף היד.\nקרוב לכל מה שחשוב.").font(.largeTitle.bold()).multilineTextAlignment(.center)
            Text("הדמות שלך, הקול שלך, העוזר שלך.").foregroundStyle(.secondary)
            Button{showPairing=true}label:{Label("חיבור מכשיר קרוב",systemImage:"antenna.radiowaves.left.and.right").frame(maxWidth:.infinity).padding(8)}.buttonStyle(.borderedProminent).controlSize(.large)
            HubLogin(client:client)
        }.padding(25)}
    }
    private var settings:some View {
        NavigationStack{Form{
            Section("המכשיר שלי"){
                DeviceInfoCard(device:client.device,hardware:bluetooth.hardware,connected:client.connected)
                FirmwareUpdateCard(updates:firmwareUpdates,device:client.device,fixture:client.uiTesting)
                Button("רשת Wi‑Fi ומכשיר"){bluetooth.beginSetup();showSettings=false;showPairing=true}
                Button("דמויות ויצירת Pip"){showSettings=false;showPips=true}
            }
            Section("שיחה"){
                ForEach(client.providers){p in Button("שיחה חדשה עם \(p.id == "codex" ? "Codex":"Claude Code")"){Task{await client.newSession(p.id);showSettings=false}}.disabled(!p.available || client.busy)}
                NavigationLink("קול ודיבור"){VoiceSettings(client:client)}
                Toggle("תמלול בזמן הדיבור",isOn:Binding(get:{client.preferences.live_transcription ?? false},set:{value in Task{await client.setting("live_transcription",value);try? await client.refresh()}}))
                Text("תמלול חי בעברית בזמן ההקלטה. הטקסט הסופי עשוי להתעדכן בשחרור הכפתור.").font(.caption).foregroundStyle(.secondary)
            }
            Section("מראה ותחושה"){
                Picker("תצוגה",selection:$appearance){Text("לפי המערכת").tag("system");Text("בהיר").tag("light");Text("כהה").tag("dark")}
                Toggle("הצגת הדמות הצפה",isOn:Binding(get:{!pipHidden},set:{pipHidden = !$0}))
                Toggle("צלילי הדמויות באפליקציה",isOn:$characterSounds)
                Toggle("תגובה לניעור המכשיר",isOn:Binding(get:{client.preferences.shake_reaction ?? true},set:{value in Task{await client.setting("shake_reaction",value);try? await client.refresh()}}))
                Toggle("צלילי הדמויות במכשיר",isOn:Binding(get:{client.preferences.character_sounds ?? true},set:{value in Task{await client.setting("character_sounds",value);try? await client.refresh()}}))
            }
            Section {
                NavigationLink("מסך, קול וסוללה"){Form{Section{DeviceSliders(client:client)};Section{PowerSettings(client:client)}}.navigationTitle("המכשיר")}
                NavigationLink("פרטי חיבור"){Form{Section{HubLogin(client:client)};Section{if let version=client.device.fw_version{LabeledContent("גרסה",value:version)};NavigationLink("דגמי Wappai"){DeviceShowroom()}}}.navigationTitle("פרטי חיבור")}
            }
            Section{Text("רשתות Wi‑Fi בתדר 2.4GHz. במצב שינה עמוקה המכשיר אינו זמין מרחוק; BOOT מעיר אותו.").font(.footnote).foregroundStyle(.secondary)}
        }.navigationTitle("הגדרות").toolbar{ToolbarItem(placement:.confirmationAction){Button("סיום"){showSettings=false}}}}
    }
}
struct HubLogin:View {
    @ObservedObject var client:WappaiClient
    @State private var code=""
    var body:some View {VStack(alignment:.leading,spacing:12){
        Text(client.paired ? "שרת Wappai":"חיבור לצ׳אט").font(.headline)
        TextField("https://hub.example",text:$client.server).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL).environment(\.layoutDirection,.leftToRight).textFieldStyle(.roundedBorder)
        if !client.paired {Text("קוד החיבור החד־פעמי מופיע בניהול השרת שלך.").font(.caption).foregroundStyle(.secondary)
            HStack{TextField("קוד בן 6 ספרות",text:$code).keyboardType(.numberPad).textFieldStyle(.roundedBorder);Button("התחברות"){Task{await client.pair(code:code)}}.disabled(code.count != 6)}
        }
        if !client.error.isEmpty{Text(client.error).font(.caption).foregroundStyle(.orange)}
    }}
}
struct DeviceSliders:View {
    @ObservedObject var client:WappaiClient
    @State private var brightness=170.0
    @State private var volume=80.0
    var body:some View{VStack{HStack{Image(systemName:"sun.max");Slider(value:$brightness,in:20...255,onEditingChanged:{editing in if !editing{Task{await client.setting("brightness",Int(brightness))}}}).accessibilityLabel("בהירות")}
        HStack{Image(systemName:"speaker.wave.2");Slider(value:$volume,in:0...100,onEditingChanged:{editing in if !editing{Task{await client.setting("volume",Int(volume))}}}).accessibilityLabel("עוצמת קול")}}.onAppear{brightness=Double(client.preferences.brightness ?? 170);volume=Double(client.preferences.volume ?? 80)}}
}
struct PairingView: View {
    @ObservedObject var bluetooth: WappaiBluetooth
    @Environment(\.dismiss) private var dismiss
    @State private var selected:WappaiBluetooth.Network?
    var body: some View {
        NavigationStack {
            Group {
                if bluetooth.joining || bluetooth.wifiConnected {
                    VStack(spacing:16){
                        WappaiDevice3D(hardware:bluetooth.hardware).frame(height:205)
                        if bluetooth.wifiConnected {Image(systemName:"checkmark.circle.fill").font(.largeTitle).foregroundStyle(.green)} else {ProgressView()}
                        Text(bluetooth.status).font(.headline).multilineTextAlignment(.center)
                        if bluetooth.wifiConnected {Button("סיום"){dismiss()}.buttonStyle(.borderedProminent)}
                        Spacer(minLength:0)
                    }.padding(24)
                } else if bluetooth.paired {
                    List {
                        Section {
                            ForEach(bluetooth.networks) { network in
                                Button { if network.open {bluetooth.join(ssid:network.ssid,password:"")} else {selected=network} } label: {
                                    HStack(spacing:12) {
                                        Image(systemName:"wifi").foregroundStyle(.secondary)
                                        Text(network.ssid).foregroundStyle(.primary)
                                        Spacer()
                                        if !network.open {Image(systemName:"lock.fill").font(.footnote).foregroundStyle(.secondary)}
                                        Image(systemName:"chevron.forward").font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
                                    }.padding(.vertical,5)
                                }
                            }
                            if bluetooth.scanning {HStack{ProgressView();Text("מחפש רשתות…").foregroundStyle(.secondary)}}
                            else if bluetooth.networks.isEmpty {Text("לא נמצאו רשתות בקרבת המכשיר").foregroundStyle(.secondary)}
                        } footer: {Text("בחר רשת 2.4GHz בקרבת Wappai.")}
                        if !bluetooth.status.isEmpty {Section{Text(bluetooth.status).font(.footnote).foregroundStyle(.secondary)}}
                    }.navigationTitle("בחירת רשת")
                    .toolbar{ToolbarItem(placement:.topBarLeading){Button{bluetooth.scanNetworks()}label:{Image(systemName:"arrow.clockwise")}.accessibilityLabel("סריקת רשתות")}}
                } else {
                    VStack(spacing:12) {
                        WappaiDevice3D(hardware:bluetooth.hardware).frame(height:154).padding(.top,4)
                        Text("Wappai בקרבתך").font(.title2.bold())
                        Text(bluetooth.status.isEmpty ? "החבר הקטן שלך, מוכן להכיר אותך." : bluetooth.status)
                            .font(.subheadline).multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth:300)
                        if let device=bluetooth.nearby.first {
                            Button{bluetooth.connect(device)}label:{Text("התחברות").font(.headline).frame(maxWidth:.infinity).padding(.vertical,9)}
                                .buttonStyle(.borderedProminent).controlSize(.large).padding(.top,4)
                        } else {ProgressView("מחפש את Wappai…").padding(.top,6)}
                        Spacer(minLength:0)
                    }.padding(.horizontal,28)
                }
            }
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button { dismiss() } label:{Image(systemName:"xmark")} .accessibilityLabel("סגירה") } }
            .navigationBarTitleDisplayMode(.inline)
        }
        .sheet(item:$selected){network in NetworkPasswordSheet(bluetooth:bluetooth,network:network).presentationDetents([.medium]).presentationDragIndicator(.visible)}
    }
}
struct NetworkPasswordSheet:View {
    @ObservedObject var bluetooth:WappaiBluetooth
    let network:WappaiBluetooth.Network
    @Environment(\.dismiss) private var dismiss
    @FocusState private var passwordFocused:Bool
    @State private var password=""
    var body:some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing:10){
                        Image(systemName:"wifi").font(.system(size:32,weight:.medium)).foregroundStyle(.tint)
                        Text(network.ssid).font(.title3.weight(.semibold))
                        Text("הזן את סיסמת הרשת כדי לחבר את Wappai.").font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    }.frame(maxWidth:.infinity).padding(.vertical,10).listRowBackground(Color.clear)
                }
                Section {
                    SecureField("סיסמה",text:$password).textContentType(.password).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .focused($passwordFocused).submitLabel(.join).onSubmit{join()}
                }
            }
            .navigationTitle("התחברות לרשת").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement:.cancellationAction){Button("ביטול"){dismiss()}}
                ToolbarItem(placement:.confirmationAction){Button("הצטרפות"){join()}.fontWeight(.semibold).disabled(password.utf8.count<8 || password.utf8.count>63)}
            }
        }
    }
    private func join(){guard password.utf8.count>=8 && password.utf8.count<=63 else{return};bluetooth.join(ssid:network.ssid,password:password);password="";dismiss()}
}

struct PowerSettings:View {
    @ObservedObject var client:WappaiClient
    @State private var hold=false
    @State private var reduced=false
    @State private var sleep=300
    var body:some View {
        Toggle("החזקת BOOT בזמן דיבור",isOn:$hold).onChange(of:hold){_,v in Task{await client.setting("hold_to_talk",v)}}
        Toggle("הפחתת תנועה",isOn:$reduced).onChange(of:reduced){_,v in Task{await client.setting("reduced_motion",v)}}
        Picker("שינה עמוקה ללא פעילות",selection:$sleep){Text("דקה").tag(60);Text("5 דקות").tag(300);Text("15 דקות").tag(900)}
            .onChange(of:sleep){_,v in Task{await client.setting("sleep_seconds",v)}}
            .onAppear{hold=client.preferences.hold_to_talk ?? false;reduced=client.preferences.reduced_motion ?? false;sleep=client.preferences.sleep_seconds ?? 300}
    }
}
