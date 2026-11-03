import SwiftUI

@MainActor final class FirmwareUpdates: ObservableObject {
    @Published var checking=false
    @Published var message="בדיקת גרסאות לפי הדגם המחובר"
    @Published var available:FirmwareRelease?
    @Published var notice:FirmwareRelease?
    private var checked:[String:Date]=[:]
    private var selectedKey=""
    private var activeKey:String?
    private static let catalogURL=URL(string:"https://raw.githubusercontent.com/rotem221/Wappai/main/release/firmware-catalog.json")!
    func check(board:String?, version:String?, manual:Bool=false, fixture:Bool=false) async {
        let key=(board ?? "")+":"+(version ?? "")
        if selectedKey != key {available=nil;notice=nil;selectedKey=key}
        guard let board,!board.isEmpty,let version,FirmwareVersion(version) != nil else {
            available=nil;message="יש לחבר מכשיר שמדווח על דגם וגרסת קושחה.";return
        }
        if activeKey==key{return}
        while activeKey != nil {
            do {try await Task.sleep(for:.milliseconds(50))}catch{return}
            guard selectedKey==key else{return}
        }
        guard !Task.isCancelled else{return}
        if !manual,let last=checked[key],Date().timeIntervalSince(last)<86400{return}
        activeKey=key;checking=true;message="בודק עדכונים ב־GitHub…"
        defer {activeKey=nil;checking=false}
        do {
            // Isolated UI tests never access accounts, devices or GitHub.
            if fixture {message="הגרסה מעודכנת — בדיקת ממשק מקומית";checked[key]=Date();return}
            var request=URLRequest(url:Self.catalogURL,cachePolicy:.reloadIgnoringLocalCacheData,timeoutInterval:15)
            request.setValue("application/json",forHTTPHeaderField:"Accept")
            let (data,response)=try await URLSession.shared.data(for:request)
            guard let response=response as? HTTPURLResponse,response.statusCode==200,data.count<131072 else{throw URLError(.badServerResponse)}
            let catalog=try JSONDecoder().decode(FirmwareCatalog.self,from:data)
            guard selectedKey==key else{return}
            guard let target=catalog.board(board) else{throw URLError(.cannotParseResponse)}
            checked[key]=Date();available=nil
            guard target.status=="available",let release=target.release else {
                message="עדיין אין קושחה מאומתת להפצה לדגם הזה.";return
            }
            guard release.isValid,let installed=FirmwareVersion(version),let latest=FirmwareVersion(release.version),
                  URLComponents(string:release.install_url)?.queryItems?.first(where:{$0.name=="board"})?.value==board else{throw URLError(.cannotParseResponse)}
            if latest>installed {
                available=release;message="זמין עדכון \(release.package_version) לדגם שלכם."
                let notificationKey="wappai.update.notice."+board+"."+release.package_version
                if !manual && !UserDefaults.standard.bool(forKey:notificationKey){
                    notice=release;UserDefaults.standard.set(true,forKey:notificationKey)
                }
            } else {message=latest==installed ? "זו הגרסה האחרונה שפורסמה לדגם שלכם.":"המכשיר מריץ גרסה חדשה יותר מהקטלוג הציבורי."}
        } catch {
            if selectedKey==key {available=nil;message="לא ניתן לבדוק עדכונים כרגע. אפשר לנסות שוב.";checked[key]=Date().addingTimeInterval(-85800)}
        }
    }
}

struct FirmwareUpdateCard:View {
    @ObservedObject var updates:FirmwareUpdates
    let device:DeviceStatus
    var fixture=false
    var body:some View {
        VStack(alignment:.leading,spacing:12){
            Button {Task{await updates.check(board:device.board,version:device.fw_version,manual:true,fixture:fixture)}} label: {
                HStack {Label("בדיקת עדכונים",systemImage:"arrow.triangle.2.circlepath");Spacer();if updates.checking{ProgressView()}}
            }.disabled(updates.checking || device.board==nil).accessibilityIdentifier("checkFirmwareUpdates")
            Text(updates.message).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("firmwareUpdateStatus")
            if let release=updates.available {
                if let url=release.releaseURL {Link("מה חדש בגרסה",destination:url)}
                if let url=release.installURL {Link("התקנת העדכון באמצעות מחשב ו־USB",destination:url)}
                Text("ההתקנה נעשית בדפדפן במחשב, לאחר גיבוי ואישור. לא מתבצעת התקנה אוטומטית.").font(.caption).foregroundStyle(.secondary)
            }
        }.padding(.vertical,4)
    }
}
