import SwiftUI

// Matches Chums' edge panel: Hebrew leading (physical right) edge, rounded inner corners,
// 84% width, scrim, a slight recession of the conversation and interactive drag.
struct ConversationDrawer:ViewModifier {
    @ObservedObject var client:WappaiClient
    @Binding var visible:Bool
    @State private var edge:CGFloat=0
    @GestureState private var closing:CGFloat=0
    @Environment(\.accessibilityReduceMotion) private var reduced
    private var motion:Animation? {reduced ? .easeOut(duration:0.12):.spring(response:0.38,dampingFraction:0.86)}
    func body(content:Content)->some View {
        GeometryReader{g in
            let width=min(330,g.size.width*0.84)
            let progress=min(1,max(0,(visible ? 1:0)+(edge+closing)/width))
            ZStack(alignment:.topTrailing){
                content.environment(\.layoutDirection,.rightToLeft)
                    .scaleEffect(reduced ? 1:1-0.06*progress,anchor:.leading)
                    .accessibilityHidden(visible)
                Color.black.opacity(0.48*progress).ignoresSafeArea()
                    .allowsHitTesting(progress>0.01).onTapGesture{withAnimation(motion){visible=false}}
                    .accessibilityLabel("סגירת תפריט השיחות")
                ConversationSidebar(client:client,visible:$visible)
                    .frame(width:width)
                    .offset(x:width*(1-progress)+24*max(0,1-progress*20))
                    .shadow(color:.black.opacity(0.25*progress),radius:24,x:-8)
                    .allowsHitTesting(progress>0.01).accessibilityHidden(progress==0)
                    .gesture(DragGesture(minimumDistance:12).updating($closing){v,s,_ in
                        if abs(v.translation.width)>abs(v.translation.height){s = -max(0,v.translation.width)}
                    }.onEnded{v in withAnimation(motion){visible=1-v.predictedEndTranslation.width/width>0.5}})
            }.environment(\.layoutDirection,.leftToRight)
                .gesture(WappaiEdgePan(enabled:client.paired && !visible,changed:{edge=max(0,-$0)},ended:{distance in
                    withAnimation(motion){edge=0;visible = -distance>width*0.5}
                }))
        }.sensoryFeedback(.selection,trigger:visible)
    }
}
struct WappaiEdgePan:UIGestureRecognizerRepresentable {
    var enabled:Bool
    var changed:(CGFloat)->Void
    var ended:(CGFloat)->Void
    func makeCoordinator(converter:CoordinateSpaceConverter)->Coordinator{Coordinator()}
    func makeUIGestureRecognizer(context:Context)->UIScreenEdgePanGestureRecognizer {
        let pan=UIScreenEdgePanGestureRecognizer();pan.edges = .right;pan.delegate=context.coordinator;return pan
    }
    func updateUIGestureRecognizer(_ pan:UIScreenEdgePanGestureRecognizer,context:Context){pan.isEnabled=enabled}
    func handleUIGestureRecognizerAction(_ pan:UIScreenEdgePanGestureRecognizer,context:Context){
        let x=pan.translation(in:pan.view).x
        switch pan.state {
        case .changed:changed(x)
        case .ended:ended(x+pan.velocity(in:pan.view).x*0.15)
        case .cancelled,.failed:ended(0)
        default:break
        }
    }
    final class Coordinator:NSObject,UIGestureRecognizerDelegate {
        func gestureRecognizer(_ gestureRecognizer:UIGestureRecognizer,shouldBeRequiredToFailBy other:UIGestureRecognizer)->Bool {
            other is UIPanGestureRecognizer && !(other is UIScreenEdgePanGestureRecognizer)
        }
    }
}
