import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import ImageIO

struct PipJob:Codable,Identifiable {
    let id:String;let pip_id:String;let name:String;let description:String
    let status:String;let progress:Int;let preview_sha:String?;let error:String?;let installed:Bool?;let asset_id:String?;let installation_error:String?;var has_reference:Bool?=nil;var target:String?=nil
    var running:Bool {["preview_generating","building","applying"].contains(status)}
    var label:String {switch status {case "preview_generating":return "Codex מעצב את הדמות…";case "preview_ready":return "העיצוב מוכן לאישור";case "building":return "יוצר ובודק את כל ההבעות והתנועות…";case "applying":return "טוען למכשיר…";case "ready":return "הדמות מוכנה";case "cancelled":return "היצירה בוטלה";default:return "היצירה לא הושלמה"}}
}
struct PipGallery:View {
    @ObservedObject var client:WappaiClient
    @Environment(\.dismiss) private var dismiss
    @State private var creating=false
    @State private var expression:PipSkin?
    @State private var editing:PipSkin?
    @State private var deleting:PipSkin?
    @State private var resumed:PipJob?
    @ObservedObject private var notifications=AppNotifications.shared
    @Environment(\.scenePhase) private var phase
    private var jobs:[PipJob] {client.pipJobs}
    private var drafts:[PipJob] {var seen=Set<String>();return jobs.filter{$0.status != "ready" && $0.status != "cancelled" && $0.status != "superseded" && seen.insert($0.pip_id).inserted}}
    @AppStorage("wappai.pip.hidden") private var hidden=false
    var body:some View {
        NavigationStack {
            VStack(spacing:0){PipCompletionBanner(client:client)
            ScrollView {VStack(spacing:22){
                Text("לכל יום, חבר אחר").font(.title2.weight(.semibold)).padding(.top)
                LazyVGrid(columns:[GridItem(.flexible()),GridItem(.flexible())],spacing:16){
                    ForEach(client.pips){pip in
                        VStack(spacing:10){
                            PipCharacter(rig:pip.rig,tint:pip.color,paused:creating || editing != nil || expression != nil || resumed != nil,frames:pip.asset_id.flatMap{client.art[$0]}).frame(height:165)
                            Text(pip.name).font(.headline)
                            if pip.builtin {Text("כלול ב־Wappai").font(.caption2).foregroundStyle(.secondary)}
                            HStack {
                                Button(client.chosenID==pip.id ? "נבחרה":"בחירה"){Task{await client.activate(pip)}}.buttonStyle(.bordered)
                                Menu {
                                    Button("הבעות וצלילים"){expression=pip}
                                    if !pip.builtin {
                                        Button("עריכת הדמות"){editing=pip}
                                        Button("מחיקה",role:.destructive){deleting=pip}
                                    }
                                }label:{Image(systemName:"ellipsis").frame(width:32,height:32)}.accessibilityLabel("אפשרויות עבור \(pip.name)").accessibilityIdentifier("pipOptions-"+pip.id)
                            }
                        }.padding(12).background(Color(uiColor:.secondarySystemBackground),in:RoundedRectangle(cornerRadius:28)).task(id:pip.asset_id){await client.loadArt(pip)}
                    }
                    ForEach(drafts){job in
                        Button{resumed=job}label:{PipDraftCard(client:client,job:job)}.buttonStyle(.plain).accessibilityIdentifier("pipDraft-"+job.id)
                    }
                }
                Button{creating=true}label:{Label("יצירת Pip חדש",systemImage:"sparkles").frame(maxWidth:.infinity).padding(10)}.buttonStyle(.borderedProminent)
                if hidden {Button("הצגת הדמות הצפה בצ׳אט"){hidden=false}}
                if !client.error.isEmpty {Text(client.error).font(.caption).foregroundStyle(.orange)}
            }.padding()}}.navigationTitle("Pips")
             .toolbar{ToolbarItem(placement:.confirmationAction){Button("סיום"){dismiss()}}}
        }
        .task {await refreshJobs()
            #if DEBUG
            let args=ProcessInfo.processInfo.arguments
            if args.contains("--create-pip"){creating=true}
            if let i=args.firstIndex(of:"--show-pip-job"),args.count>i+1 {resumed=jobs.first{$0.id==args[i+1]}}
            #endif
        }
        .task(id:phase){
            while !Task.isCancelled && phase == .active {
                if !creating && editing==nil && resumed==nil {await refreshJobs()}
                do{try await Task.sleep(for:.seconds(3))}catch{return}
            }
        }
        .task(id:notifications.pipJobID){
            if let id=notifications.pipJobID {await refreshJobs();resumed=jobs.first{$0.id==id};notifications.pipJobID=nil}
        }
        .sheet(isPresented:$creating,onDismiss:{Task{await refreshJobs()}}){CreatePipView(client:client)}
        .sheet(item:$editing,onDismiss:{Task{await refreshJobs()}}){pip in CreatePipView(client:client,target:pip)}
        .sheet(item:$resumed,onDismiss:{Task{await refreshJobs()}}){job in CreatePipView(client:client,resume:job)}
        .sheet(item:$expression){pip in ExpressionStudio(client:client,pip:pip)}
        .alert("מחיקת הדמות?",isPresented:Binding(get:{deleting != nil},set:{if !$0 {deleting=nil}})){
            Button("מחיקה",role:.destructive){if let p=deleting{Task{await client.removePip(p);await refreshJobs()}};deleting=nil}
            Button("ביטול",role:.cancel){deleting=nil}
        }message:{Text("הדמות וההבעות האישיות שלה יימחקו. שלוש דמויות ברירת המחדל יישארו זמינות.")}
    }
    private func refreshJobs() async {
        await client.refreshPipJobs()
        if !client.uiTesting && jobs.contains(where:{job in job.status=="ready" && !client.pips.contains(where: {$0.id==job.pip_id})}) {try? await client.refresh()}
    }
}
struct PipDraftCard:View {
    @ObservedObject var client:WappaiClient
    let job:PipJob
    @State private var thumbnail:UIImage?
    var body:some View {
        VStack(spacing:10){
            Group {if let thumbnail {Image(uiImage:thumbnail).resizable().interpolation(.none).scaledToFit()}
                else {ZStack{Color.accentColor.opacity(0.06);Image(systemName:"sparkles").font(.largeTitle).foregroundStyle(.secondary)}}}
                .frame(height:165)
            Text(job.name).font(.headline).lineLimit(1)
            Text(job.preview_sha != nil ? "תצוגה מקדימה":job.label).font(.caption).foregroundStyle(.secondary)
            if job.running {ProgressView(value:Double(job.progress),total:100)}
            else {Label(job.status=="failed" ? "בדיקת היצירה":"פתיחה ועריכה",systemImage:"pencil").font(.caption)}
        }.padding(12).frame(maxWidth:.infinity).background(Color(uiColor:.secondarySystemBackground),in:RoundedRectangle(cornerRadius:28))
        .task(id:job.preview_sha){if job.preview_sha != nil {thumbnail=try? UIImage(data:await client.call("/v1/pip-jobs/\(job.id)/preview.png"))}}
    }
}
struct PipCompletionBanner:View {
    @ObservedObject var client:WappaiClient
    var body:some View {
        if let notice=client.pipNotice {
            HStack{Image(systemName:"checkmark.circle.fill").foregroundStyle(.green);Text(notice).font(.subheadline);Spacer();Button{client.pipNotice=nil}label:{Image(systemName:"xmark").frame(width:36,height:36)}.accessibilityLabel("סגירת ההתראה")}
                .padding(10).background(.regularMaterial,in:RoundedRectangle(cornerRadius:20)).padding(.horizontal).accessibilityIdentifier("pipCompletionNotice")
        }
    }
}
struct CreatePipView:View {
    @ObservedObject var client:WappaiClient
    var target:PipSkin?=nil
    var resume:PipJob?=nil
    @Environment(\.dismiss) private var dismiss
    @State private var name=""
    @State private var brief=""
    @State private var photo:PhotosPickerItem?
    @State private var reference:Data?
    @State private var preview:UIImage?
    @State private var job:PipJob?
    @State private var working=false
    @State private var error=""
    @State private var importing=false
    @State private var loadingPhoto=false
    @State private var loadedDraft=false
    @State private var referenceCleared=false
    @State private var editingTarget:String?
    @State private var replacingJob:String?
    @State private var sourcePath:String?
    @State private var sourceFailed=false
    @State private var previewKey=""
    var body:some View {
        NavigationStack {VStack(spacing:0){PipCompletionBanner(client:client);Form {
            if let job {
                Section {
                    if let preview {Image(uiImage:preview).resizable().interpolation(.none).scaledToFit().frame(height:240).frame(maxWidth:.infinity)}
                    Text(job.label).font(.headline)
                    if job.running {ProgressView(value:Double(job.progress),total:100);Text("אפשר לסגור את החלון. היצירה נשמרת ותמשיך ברקע.").font(.caption).foregroundStyle(.secondary)}
                    if let message=job.error,!message.isEmpty {Text(message).foregroundStyle(.orange)}
                    if job.status=="preview_ready" || job.status=="failed" && job.preview_sha != nil {
                        Text("אישור ייצור 24 תנוחות ואת כל רצפי ההאזנה, החשיבה, הדיבור, השינה וההבעות, וישמור את הדמות רק לאחר בדיקת החבילה.").font(.footnote).foregroundStyle(.secondary)
                        Button("אישור ויצירה מלאה"){Task{await apply()}}.disabled(working)
                        Button("שינוי העיצוב ויצירת תצוגה חדשה"){replacingJob=job.id;self.job=nil;preview=nil;previewKey=""}
                    }
                    if job.status=="failed" && job.preview_sha==nil || job.status=="cancelled" {Button("ניסיון חדש"){replacingJob=job.id;self.job=nil;preview=nil;previewKey=""}}
                    if job.running {Button("ביטול היצירה",role:.destructive){Task{await cancel()}}.disabled(job.status=="applying" || working)}
                    if job.status=="ready" {
                        Text(job.installed==true ? "הדמות נשמרה ונטענה למכשיר.":"הדמות נשמרה בגלריה. ניתן לבחור בה כשהמכשיר מחובר.").font(.subheadline)
                        if job.installed != true {
                            if let message=job.installation_error,!message.isEmpty {Text(message).font(.caption).foregroundStyle(.orange)}
                            Button("טעינה למכשיר"){Task{await install(job)}}.disabled(working)
                        }
                        Button("מעבר לגלריה"){dismiss()}
                    }
                }
            }else {
                Section("הדמות שלך") {
                    if reference==nil {TextField("שם הדמות",text:$name)}
                    TextField(reference==nil ? "תיאור הדמות, הצבעים והאופי…":"תיאור או הנחיות לתמונה (אפשרות)",text:$brief,axis:.vertical).lineLimit(3...6).accessibilityIdentifier("pipDescription")
                    if let reference,let image=UIImage(data:reference){
                        Image(uiImage:image).resizable().scaledToFit().frame(height:200).frame(maxWidth:.infinity).accessibilityLabel("התמונה שנבחרה")
                        Text("ניצור מהתמונה דמות בסגנון הפיקסלים של Wappai, מותאמת למסך המכשיר. אפשר להוסיף תיאור או להשאיר את התמונה כפי שהיא.").font(.footnote).foregroundStyle(.secondary)
                        Button("הסרת התמונה",role:.destructive){self.reference=nil;photo=nil;referenceCleared=true;sourceFailed=false}
                    }
                    if loadingPhoto {ProgressView("טוען את התמונה…")}
                    PhotosPicker(selection:$photo,matching:.images){Label("תמונה מהספרייה",systemImage:"photo")}
                    Button{importing=true}label:{Label("תמונה מקובץ",systemImage:"folder")}
                }.disabled(working || loadingPhoto)
                Section {
                    Text("Codex יכין עיצוב מקורי בסגנון פיקסלים לפי התיאור או התמונה. תחילה תראו תצוגה מקדימה; האנימציות ייווצרו רק לאחר אישור.").font(.footnote).foregroundStyle(.secondary)
                    Button(working ? "מתחיל…":reference==nil ? "יצירת תצוגה מקדימה":"אישור התמונה ויצירת תצוגה מקדימה"){Task{await create()}}
                        .disabled(working || loadingPhoto || sourceFailed || brief.count>1200 || reference==nil && (name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || name.count>30 || brief.count>1200 || brief.trimmingCharacters(in:.whitespacesAndNewlines).count<3))
                }
                if let target {
                    Section {Button("שמירת השם בלבד"){Task{await rename(target)}}.disabled(working || name.isEmpty || name.count>30)}
                }
            }
            if !error.isEmpty {Section{Text(error).foregroundStyle(.orange);if sourceFailed,let sourcePath {Button("טעינת תמונת המקור מחדש"){Task{await loadSource(sourcePath)}}}}}
        }}.navigationTitle(target==nil ? "חבר חדש":"עריכת הדמות")
         .toolbar{ToolbarItem(placement:.confirmationAction){Button("סגירה"){dismiss()}}}
        }
        .task {
            guard !loadedDraft else{return};loadedDraft=true
            name=resume?.name ?? target?.name ?? "";brief=resume?.description ?? target?.description ?? "";job=resume;editingTarget=resume?.target ?? target?.id;replacingJob=resume?.id
            loadingPhoto=true;defer{loadingPhoto=false}
            let path:String?
            if let resume,resume.has_reference==true {path="/v1/pip-jobs/\(resume.id)/reference.png"}
            else if let target,target.asset_id != nil {path="/v1/pips/\(target.id)/reference.png"}
            else {path=nil}
            if let path {sourcePath=path;await loadSource(path)}
        }
        .task(id:job?.id){await poll()}
        .task(id:photo){
            guard let photo else{return}
            reference=nil;loadingPhoto=true;error="";defer{loadingPhoto=false}
            do {
                guard let data=try await photo.loadTransferable(type:Data.self) else{throw URLError(.cannotDecodeContentData)}
                try Task.checkCancellation();try attach(data)
            }catch{if !Task.isCancelled {self.error="לא ניתן לקרוא את התמונה. בחרו תמונה ברורה בגודל 32×32 פיקסלים לפחות ונסו שוב."}}
        }
        .fileImporter(isPresented:$importing,allowedContentTypes:[.image]){result in
            do{let url=try result.get();let access=url.startAccessingSecurityScopedResource();defer{if access{url.stopAccessingSecurityScopedResource()}};reference=nil;try attach(Data(contentsOf:url))}catch{self.error="לא ניתן לפתוח את התמונה. בחרו קובץ תמונה תקין בגודל 32×32 פיקסלים לפחות."}
        }
    }
    private func loadSource(_ path:String) async {
        loadingPhoto=true;defer{loadingPhoto=false}
        do{try attach(await client.call(path));sourceFailed=false}
        catch{sourceFailed=true;self.error="לא ניתן לטעון את תמונת המקור. נסו שוב כשיש חיבור."}
    }
    private func attach(_ data:Data) throws {
        reference=nil
        guard data.count<30_000_000,let source=CGImageSourceCreateWithData(data as CFData,nil),let image=CGImageSourceCreateThumbnailAtIndex(source,0,[kCGImageSourceCreateThumbnailFromImageAlways:true,kCGImageSourceThumbnailMaxPixelSize:1280,kCGImageSourceCreateThumbnailWithTransform:true] as CFDictionary),min(image.width,image.height)>=32,let png=UIImage(cgImage:image).pngData(),png.count<6_000_000 else{throw URLError(.cannotDecodeContentData)}
        reference=png;referenceCleared=false;sourceFailed=false;error=""
    }
    private func create() async {
        working=true;error="";defer{working=false}
        do {var body:[String:Any]=["name":name,"description":brief,"discard_reference":referenceCleared]
            if let reference{body["reference"]=reference.base64EncodedString()};if let editingTarget{body["target"]=editingTarget};if let replacingJob{body["replaces_job"]=replacingJob}
            job=try JSONDecoder().decode(PipJob.self,from:await client.call("/v1/pip-jobs",body:body,timeout:40))
            if let job {client.recordPipJob(job)}
        }catch{self.error=error.localizedDescription}
    }
    private func apply() async {guard let job,let sha=job.preview_sha else{return};working=true;error="";defer{working=false};do{self.job=try JSONDecoder().decode(PipJob.self,from:await client.call("/v1/pip-jobs/\(job.id)/apply",body:["preview_sha":sha]));}catch{self.error=error.localizedDescription}}
    private func install(_ job:PipJob) async {working=true;error="";defer{working=false};do{try await client.call("/v1/pips/\(job.pip_id)/activate",body:[:],timeout:75);try await client.refresh()}catch{self.error=error.localizedDescription}}
    private func cancel() async {guard let job else{return};working=true;defer{working=false};do{try await client.call("/v1/pip-jobs/\(job.id)/cancel",body:[:]);self.job=try JSONDecoder().decode(PipJob.self,from:await client.call("/v1/pip-jobs/\(job.id)"))}catch{self.error=error.localizedDescription}}
    private func rename(_ pip:PipSkin) async {working=true;defer{working=false};do{try await client.call("/v1/pips/\(pip.id)/edit",body:["name":name],timeout:75);try await client.refresh();dismiss()}catch{self.error=error.localizedDescription}}
    private func poll() async {
        guard let id=job?.id else{return}
        while !Task.isCancelled && job?.id==id {
            do {
                let fresh=try JSONDecoder().decode(PipJob.self,from:await client.call("/v1/pip-jobs/\(id)"));job=fresh;client.recordPipJob(fresh)
                if let sha=fresh.preview_sha,sha != previewKey {preview=UIImage(data:try await client.call("/v1/pip-jobs/\(id)/preview.png"));previewKey=sha}
                if fresh.status=="ready" {try await client.refresh()}
                error=""
            }catch{if Task.isCancelled{return};self.error="החיבור הופסק. מנסה לעדכן את מצב היצירה…"}
            do{try await Task.sleep(for:.seconds(job?.running==true ? 2:5))}catch{return}
        }
    }
}
