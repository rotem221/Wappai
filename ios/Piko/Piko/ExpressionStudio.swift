import SwiftUI
struct ExpressionStudio:View {
    @ObservedObject var client:WappaiClient
    let pip:PipSkin
    @Environment(\.dismiss) private var dismiss
    @State private var pose=PipExpression.named("happy")
    @State private var saved:[PipExpression]=[]
    @State private var brief=""
    @State private var generating=false
    @State private var status=""
    @State private var advanced=false
    @AppStorage("wappai.characterSounds") private var sounds=true
    var body:some View {
        NavigationStack {
            ScrollView {
                VStack(spacing:18){
                    PipCharacter(rig:pip.rig,tint:pip.color,expression:pose,frames:pip.asset_id.flatMap{client.art[$0]}).frame(height:270)
                    Text(pose.name).font(.title2.bold())
                    ScrollView(.horizontal){HStack(spacing:8){ForEach(PipExpression.presets){p in
                        Button(p.name){select(p)}.buttonStyle(.bordered).tint(pose.id==p.id ? .accentColor:.secondary)
                    }}}.scrollIndicators(.hidden)
                    VStack(alignment:.leading,spacing:12){
                        Text("איזו הבעה ליצור?").font(.headline)
                        TextField("למשל: סקרן, מביט לצד ומרים יד בביישנות",text:$brief,axis:.vertical).lineLimit(2...4).padding(14).wappaiGlass(radius:20)
                        Button{Task{await generate()}}label:{HStack{if generating{ProgressView()}else{Image(systemName:"sparkles")};Text(generating ? "יוצר הבעה…":"יצירת הבעה לפי התיאור")}.frame(maxWidth:.infinity).padding(8)}.buttonStyle(.borderedProminent).disabled(generating || brief.count<3 || brief.count>600 || !client.paired)
                    }.padding(18).background(Color(uiColor:.secondarySystemBackground),in:RoundedRectangle(cornerRadius:26))
                    DisclosureGroup("עריכת תנועה וצליל",isExpanded:$advanced){
                        VStack(spacing:16){
                            TextField("שם ההבעה",text:$pose.name).textFieldStyle(.roundedBorder)
                            Picker("הבעה ותנועה",selection:$pose.motion){ForEach(PipExpression.presets){p in Text(p.name).tag(p.id)}}
                            slider("מבט לצד",$pose.gazeX,-1...1)
                            slider("מבט למעלה",$pose.gazeY,-1...1)
                            slider("הטיית גוף",$pose.tilt,-0.35...0.35)
                            slider("קפיצה",$pose.bounce,0...0.2)
                            slider("קצב",$pose.speed,0.3...2)
                            Picker("צליל",selection:$pose.cue){Text("שקט").tag("none");Text("רך").tag("soft");Text("שמחה").tag("joy");Text("מחשבה").tag("think");Text("סקרנות").tag("curious");Text("שלום").tag("hello")}
                            Button("האזנה לצליל"){PipSound.shared.play(rig:pip.rig,cue:pose.cue,preview:true)}
                        }.padding(.top,14)
                    }.padding(18).background(Color(uiColor:.secondarySystemBackground),in:RoundedRectangle(cornerRadius:26))
                    HStack{
                        Button("שמירה בספרייה"){Task{await save()}}.buttonStyle(.borderedProminent).disabled(!client.paired || generating || pose.name.isEmpty)
                        Button("ניגון במכשיר"){Task{await play()}}.buttonStyle(.bordered).disabled(!client.device.online || generating)
                    }
                    if !status.isEmpty{Text(status).font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)}
                    if !saved.isEmpty {
                        VStack(alignment:.leading,spacing:12){Text("ההבעות של \(pip.name)").font(.headline)
                            ForEach(saved){p in HStack{Button(p.name){select(p)};Spacer();Button(role:.destructive){Task{await delete(p)}}label:{Image(systemName:"trash")}.accessibilityLabel("מחיקת \(p.name)")}}
                        }.padding(18).wappaiGlass(radius:24)
                    }
                }.padding(20)
            }.navigationTitle("הסטודיו של \(pip.name)").navigationBarTitleDisplayMode(.inline)
             .toolbar{ToolbarItem(placement:.confirmationAction){Button("סיום"){dismiss()}}}
             .task{await load()}
        }.onDisappear{PipSound.shared.stop()}
    }
    private func slider(_ title:String,_ value:Binding<Float>,_ range:ClosedRange<Float>)->some View {VStack(alignment:.leading){Text(title).font(.subheadline);Slider(value:value,in:range).accessibilityLabel(title)}}
    private func select(_ p:PipExpression){pose=p;if sounds{PipSound.shared.play(rig:pip.rig,cue:p.cue,preview:true)}}
    private func body(_ p:PipExpression)->[String:Any]{(try? JSONSerialization.jsonObject(with:JSONEncoder().encode(p)) as? [String:Any]) ?? [:]}
    private func load() async {guard client.paired else{return};do{saved=try JSONDecoder().decode([PipExpression].self,from:await client.call("/v1/pips/\(pip.id)/expressions"))}catch{status=error.localizedDescription}}
    private func generate() async {
        generating=true;status="";defer{generating=false}
        do{let data=try await client.call("/v1/pips/\(pip.id)/expressions/preview",body:["description":brief],timeout:115);select(try JSONDecoder().decode(PipExpression.self,from:data));status="ההבעה מוכנה לתצוגה מקדימה. אפשר לערוך ולשמור."}catch{status=error.localizedDescription}
    }
    private func save() async {do{try await client.call("/v1/pips/\(pip.id)/expressions",body:body(pose),timeout:75);await load();status="ההבעה נשמרה"}catch{status=error.localizedDescription}}
    private func play() async {do{try await client.call("/v1/pips/\(pip.id)/expressions/play",body:body(pose),timeout:75);client.choose(pip);status="ההבעה מופעלת במכשיר"}catch{status=error.localizedDescription}}
    private func delete(_ p:PipExpression) async {do{try await client.call("/v1/pips/\(pip.id)/expressions/\(p.id)/delete",body:[:]);await load()}catch{status=error.localizedDescription}}
}
