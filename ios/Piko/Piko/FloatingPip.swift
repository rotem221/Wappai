import SwiftUI

struct FloatingPip:View {
    @ObservedObject var client:WappaiClient
    var paused:Bool
    var open:()->Void
    @AppStorage("wappai.pip.hidden") private var hidden=false
    @AppStorage("wappai.pip.x") private var x=1.0
    @AppStorage("wappai.pip.y") private var y=1.0
    @State private var drag:CGSize = .zero
    @State private var lifting=false
    @State private var pressStarted:Date?
    @State private var liftTask:Task<Void,Never>?
    @GestureState private var touching=false
    @State private var menu=false
    private func resetPress(){liftTask?.cancel();liftTask=nil;pressStarted=nil;lifting=false;drag = .zero}
    private func interaction(width:CGFloat,height:CGFloat)->some Gesture {
        DragGesture(minimumDistance:0)
                        .updating($touching){_,state,_ in state=true}
                    .onChanged{value in
                            if pressStarted == nil {
                                pressStarted=Date()
                                liftTask=Task { @MainActor in
                                    try? await Task.sleep(for:.milliseconds(450))
                                    if !Task.isCancelled {lifting=true}
                                }
                            }
                            if Date().timeIntervalSince(pressStarted ?? Date()) >= 0.45 {drag=value.translation}
                        }
                        .onEnded{value in
                            let held=Date().timeIntervalSince(pressStarted ?? Date()) >= 0.45
                            if held {
                                let translation=value.translation
                                if hypot(translation.width,translation.height)<10 {menu=true}
                                else {x=min(1,max(0,(x*width+translation.width)/max(1,width)));y=min(1,max(0,(y*height+translation.height)/max(1,height)))}
                            } else if hypot(value.translation.width,value.translation.height)<10 {open()}
                            resetPress()
                        }
    }
    private func companion(width:CGFloat,height:CGFloat)->some View {
        PipCharacter(rig:client.chosenPip,tint:client.chosenColor,state:client.state,paused:paused,frames:client.selectedSkin?.asset_id.flatMap{client.art[$0]})
                    .frame(width:94,height:84).contentShape(Rectangle())
                    .scaleEffect(lifting ? 1.08:1).animation(.snappy(duration:0.18),value:lifting)
                    .gesture(interaction(width:width,height:height))
                    .onChange(of:touching){_,active in
                        if !active {resetPress()}
                    }
                    .onDisappear{resetPress()}
    }
    private func accessibleCompanion(width:CGFloat,height:CGFloat)->some View {
        companion(width:width,height:height)
                    .accessibilityElement(children:.ignore)
                    .accessibilityIdentifier("floatingPip")
                    .accessibilityAddTraits(.isButton)
                    .accessibilityLabel("הדמות שלי")
                    .accessibilityAction{open()}
                    .accessibilityHint("לחיצה ארוכה להצגת אפשרויות, או לחיצה ארוכה וגרירה להזזה")
                    .accessibilityAction(named:Text("הסתרת הדמות")){hidden=true}
                    .accessibilityAction(named:Text("החזרה לפינה הימנית")){x=1;y=1}
    }
    var body:some View {
        GeometryReader {geo in
            if !hidden {
                let width=max(0,geo.size.width-100),height=max(0,geo.size.height-90)
                let px=50+min(width,max(0,x*width+drag.width)),py=45+min(height,max(0,y*height+drag.height))
                accessibleCompanion(width:width,height:height)
                    .position(x:px,y:py)
            }
        }.environment(\.layoutDirection,.leftToRight)
         .confirmationDialog("הדמות הצפה",isPresented:$menu,titleVisibility:.visible){
             Button("הסתרת הדמות"){hidden=true}
             Button("החזרה לפינה הימנית"){x=1;y=1}
             Button("בחירת דמות",action:open)
             Button("ביטול",role:.cancel){}
         }message:{Text("להזזה: לחצו לחיצה ארוכה וגררו למקום הרצוי. אפשר להציג מחדש בהגדרות.")}
    }
}
