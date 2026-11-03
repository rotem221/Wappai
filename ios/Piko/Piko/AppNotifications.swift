import SwiftUI
import UserNotifications
import UIKit

@MainActor final class AppNotifications:NSObject,ObservableObject,UNUserNotificationCenterDelegate {
    static let shared=AppNotifications()
    @Published var status="ההתראות כבויות"
    @Published var enabled=UserDefaults.standard.bool(forKey:"wappai.notifications.enabled")
    @Published var openMeetings=false
    var token=""
    var installation:String {
        if let id=SecureStore.get("notifications.installation"){return id}
        let id=UUID().uuidString;SecureStore.put("notifications.installation",id);return id
    }
    override init(){super.init();UNUserNotificationCenter.current().delegate=self}
    func enable(client:WappaiClient) async {
        do {
            let allowed=try await UNUserNotificationCenter.current().requestAuthorization(options:[.alert,.sound,.badge])
            enabled=allowed;UserDefaults.standard.set(allowed,forKey:"wappai.notifications.enabled")
            if allowed {status="נרשם לשירות ההתראות…";UIApplication.shared.registerForRemoteNotifications();await sync(client:client)}
            else {status="יש לאפשר התראות בהגדרות האייפון"}
        } catch {status=error.localizedDescription}
    }
    func sync(client:WappaiClient) async {
        guard enabled,client.paired,!client.uiTesting else{return}
        if token.isEmpty {UIApplication.shared.registerForRemoteNotifications();return}
        do {
            let environment=(Bundle.main.object(forInfoDictionaryKey:"WappaiPushEnvironment") as? String)=="development" ? "sandbox":"production"
            let data=try await client.call("/v1/notifications/register",body:["installation":installation,"token":token,"environment":environment,"timers":true,"meetings":true])
            let configured=(try JSONSerialization.jsonObject(with:data) as? [String:Any])?["configured"] as? Bool ?? false
            status=configured ? "התראות טיימרים וסיכומי פגישות פעילות":"האייפון רשום; נדרש להשלים מפתח APNs בשרת"
        }catch{status="הרישום לשרת נכשל. נסה שוב: "+error.localizedDescription}
    }
    func disable(client:WappaiClient) async {
        do {try await client.call("/v1/notifications/unregister",body:["installation":installation]);enabled=false;UserDefaults.standard.set(false,forKey:"wappai.notifications.enabled");UIApplication.shared.unregisterForRemoteNotifications();status="ההתראות כבויות"}catch{status="לא ניתן לבטל בשרת כרגע. נסה שוב או כבה התראות בהגדרות האייפון."}
    }
    nonisolated func userNotificationCenter(_ center:UNUserNotificationCenter,willPresent notification:UNNotification,withCompletionHandler completionHandler:@escaping(UNNotificationPresentationOptions)->Void){completionHandler([.banner,.sound])}
    nonisolated func userNotificationCenter(_ center:UNUserNotificationCenter,didReceive response:UNNotificationResponse,withCompletionHandler completionHandler:@escaping()->Void){let meeting=response.notification.request.content.userInfo["kind"] as? String == "meetings";Task{@MainActor in if meeting{self.openMeetings=true}};completionHandler()}
}
class WappaiAppDelegate:NSObject,UIApplicationDelegate {
    func application(_ application:UIApplication,didRegisterForRemoteNotificationsWithDeviceToken deviceToken:Data){Task{@MainActor in AppNotifications.shared.token=deviceToken.map{String(format:"%02x",$0)}.joined();NotificationCenter.default.post(name:Notification.Name("WappaiPushToken"),object:nil)}}
    func application(_ application:UIApplication,didFailToRegisterForRemoteNotificationsWithError error:Error){Task{@MainActor in AppNotifications.shared.status="הרישום ל־APNs נכשל: "+error.localizedDescription}}
}
struct NotificationSettings:View {
    @ObservedObject var client:WappaiClient
    @ObservedObject var notifications=AppNotifications.shared
    var body:some View {Section("התראות"){
        Button(notifications.enabled ? "ביטול התראות":"הפעלת התראות"){Task{if notifications.enabled{await notifications.disable(client:client)}else{await notifications.enable(client:client)}}}.disabled(!client.paired)
        Text(notifications.status).font(.caption).foregroundStyle(.secondary)
        Text("טיימר שהסתיים וסיכום פגישה מוכן. תוכן הפגישה אינו נכלל בהתראה. השרת חייב להיות פעיל ומוגדר לשליחה.").font(.caption).foregroundStyle(.secondary)
    }}
}
