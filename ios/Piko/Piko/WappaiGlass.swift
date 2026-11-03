import SwiftUI
extension View {
    @ViewBuilder func wappaiGlass(radius:CGFloat=28) -> some View {
        if #available(iOS 26.0,*) {self.glassEffect(.regular,in:RoundedRectangle(cornerRadius:radius,style:.continuous))}
        else {self.background(.ultraThinMaterial,in:RoundedRectangle(cornerRadius:radius,style:.continuous))}
    }
}
struct ConversationSidebar:View {
    @ObservedObject var client:WappaiClient
    @Binding var visible:Bool
    @Environment(\.accessibilityReduceMotion) private var reduced
    @State private var deleting:ChatSession?
    @State private var deletingNow=false
    @State private var deleteError=""
    var body:some View {
                VStack(alignment:.leading,spacing:20){
                    HStack{Text("השיחות שלי").font(.largeTitle.bold());Spacer();Button(action:close){Image(systemName:"xmark").font(.body.weight(.semibold)).frame(width:40,height:40)}.accessibilityLabel("סגירה")}
                    Button{Task{await client.newSession();close()}}label:{Label("שיחה חדשה",systemImage:"square.and.pencil").frame(maxWidth:.infinity,alignment:.leading).padding(14)}.buttonStyle(.plain).wappaiGlass(radius:20).disabled(client.busy)
                    ScrollView{
                        LazyVStack(spacing:7){
                            ForEach(client.sessions){session in
                                HStack(spacing:0){
                                Button{Task{await client.select(session.id);close()}}label:{
                                    HStack(spacing:12){
                                        Image(systemName:"bubble.left").font(.title3).frame(width:28)
                                        VStack(alignment:.leading,spacing:6){
                                            Text(session.title).font(.body.weight(.medium)).lineLimit(2)
                                            Text("\(session.provider == "codex" ? "Codex":"Claude") · \(Date(timeIntervalSince1970:session.created).formatted(date:.abbreviated,time:.omitted))").font(.caption).foregroundStyle(.secondary)
                                        }
                                        Spacer(minLength:0)
                                        if session.id==client.active {Image(systemName:"checkmark").font(.caption.bold())}
                                    }.padding(14).frame(maxWidth:.infinity,alignment:.leading)
                                }.buttonStyle(.plain).disabled(client.busy || deletingNow)
                                Menu {
                                    Button("מחיקת השיחה",role:.destructive){deleting=session}
                                }label:{Image(systemName:"ellipsis").frame(width:44,height:44)}
                                 .accessibilityLabel("אפשרויות לשיחה: \(session.title)")
                                 .accessibilityIdentifier("sessionOptions-"+session.id)
                                 .disabled(deletingNow || session.id==client.active && client.busy)
                                }.background(session.id==client.active ? Color.accentColor.opacity(0.12):Color.clear,in:RoundedRectangle(cornerRadius:22))
                            }
                        }
                    }.scrollIndicators(.hidden)
                    if deletingNow {ProgressView("מוחק את השיחה…")}
                    if !deleteError.isEmpty {Text(deleteError).font(.footnote).foregroundStyle(.orange)}
                    Label(client.connected ? "מחובר ל־Wappai":"ממתין לחיבור",systemImage:client.connected ? "checkmark.circle.fill":"wifi.slash").font(.footnote).foregroundStyle(.secondary)
                }.padding(22).frame(maxHeight:.infinity)
                .background {
                    let shape=UnevenRoundedRectangle(topLeadingRadius:34,bottomLeadingRadius:34)
                    shape.fill(Color(uiColor:.secondarySystemBackground))
                        .overlay(shape.strokeBorder(.primary.opacity(0.07),lineWidth:0.5)).ignoresSafeArea().environment(\.layoutDirection,.leftToRight)
                }
                .environment(\.layoutDirection,.rightToLeft)
                .accessibilityAddTraits(.isModal)
                .alert("למחוק את השיחה?",isPresented:Binding(get:{deleting != nil},set:{if !$0 {deleting=nil}}),presenting:deleting){session in
                    Button("מחיקה",role:.destructive){
                        deleting=nil;deletingNow=true;deleteError=""
                        Task {if !(await client.deleteSession(session.id)){deleteError=client.error};deletingNow=false}
                    }
                    Button("ביטול",role:.cancel){deleting=nil}
                }message:{session in Text("השיחה ״\(session.title)״ וההודעות שלה יימחקו מ־Wappai בכל המכשירים המחוברים. לא ניתן לבטל את המחיקה.")}
    }
    private func close(){withAnimation(reduced ? nil:.spring(response:0.36,dampingFraction:0.88)){visible=false}}
}
