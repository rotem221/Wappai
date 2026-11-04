import SwiftUI

struct DeviceInfoCard:View {
    let device:DeviceStatus
    let hardware:WappaiHardware
    let connected:Bool
    private var live:Bool {device.online && connected}
    private var actualHardware:WappaiHardware {
        guard let board=device.board else{return hardware}
        if board.contains("216"){return .square216}
        if board.contains("18"){return .rectangle18}
        return .round175c
    }
    private var signal:String {
        guard live,let rssi=device.rssi,rssi < 0 else{return "—"}
        return "\(rssi > -60 ? "חזקה":rssi > -75 ? "טובה":"חלשה") · \u{2066}\(rssi) dBm\u{2069}"
    }
    var body:some View {
        VStack(alignment:.leading,spacing:16){
            HStack(spacing:12){
                WappaiDevice3D(hardware:actualHardware,animated:false).id(actualHardware)
                    .frame(width:88,height:96).allowsHitTesting(false).accessibilityHidden(true)
                VStack(alignment:.leading,spacing:5){
                    WappaiWordmark().frame(width:130,height:31)
                    Text("Waveshare · \(actualHardware.title)").font(.subheadline).foregroundStyle(.secondary)
                    Label(live ? "מחובר":connected ? "לא מחובר":"ממתין לעדכון",systemImage:live ? "checkmark.circle.fill":"circle.dotted")
                        .font(.caption).foregroundStyle(live ? Color.green:Color.secondary)
                }
                Spacer(minLength:0)
            }
            HStack(alignment:.top){
                VStack(alignment:.leading,spacing:6){
                    Text("סוללה").font(.caption).foregroundStyle(.secondary)
                    HStack(spacing:6){
                        BatteryBadge(percent:device.battery?.pct,charging:live && device.battery?.charging == true)
                        if live && device.battery?.charging == true {Text("בטעינה").font(.caption)}
                    }
                }
                Spacer()
                VStack(alignment:.leading,spacing:6){
                    Text("קליטת Wi‑Fi").font(.caption).foregroundStyle(.secondary)
                    Label(signal,systemImage:live ? "wifi":"wifi.slash").font(.subheadline)
                }
            }
            if !live,device.battery?.pct != nil {Text("הסוללה מציגה את הנתון האחרון שהתקבל.").font(.caption2).foregroundStyle(.secondary)}
            if let version=device.fw_version {LabeledContent("גרסת המכשיר",value:version).font(.caption).foregroundStyle(.secondary)}
        }.padding(.vertical,5)
    }
}

struct BatteryBadge:View {
    var percent:Int?
    var charging=false
    private var value:Int? {percent.flatMap{(0...100).contains($0) ? $0:nil}}
    private var color:Color {charging ? .green:(value ?? 100)<20 ? .red:.primary}
    var body:some View {
        HStack(spacing:2){
            ZStack {
                RoundedRectangle(cornerRadius:5).fill(color.opacity(0.15))
                GeometryReader{geo in
                    RoundedRectangle(cornerRadius:4).fill(color)
                        .frame(width:geo.size.width*CGFloat(value ?? 0)/100)
                }.padding(2)
                Text(value.map(String.init) ?? "—").font(.system(size:13,weight:.bold,design:.rounded))
                    .foregroundStyle(Color.primary)
                    .overlay {
                        Text(value.map(String.init) ?? "—").font(.system(size:13,weight:.bold,design:.rounded))
                            .foregroundStyle(Color(uiColor:.systemBackground))
                            .frame(width:38,height:22)
                            .mask(alignment:.leading){Rectangle().frame(width:2+34*CGFloat(value ?? 0)/100)}
                    }
            }.compositingGroup().frame(width:38,height:22)
             .overlay(RoundedRectangle(cornerRadius:5).strokeBorder(color.opacity(0.5),lineWidth:1))
            Capsule().fill(color.opacity(0.5)).frame(width:3,height:8)
        }.environment(\.layoutDirection,.leftToRight)
         .accessibilityElement(children:.ignore).accessibilityLabel(value.map{"סוללה \($0) אחוזים"} ?? "אחוז הסוללה אינו זמין")
    }
}
