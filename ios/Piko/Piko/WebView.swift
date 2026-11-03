import SwiftUI
import WebKit

final class WebModel: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate {
    let view: WKWebView
    @Published var failed = false
    var onAuthLost: (() -> Void)?
    private var loginDone: ((Bool, String) -> Void)?

    override init() {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()                 // keeps the login cookie between launches
        cfg.allowsInlineMediaPlayback = true
        view = WKWebView(frame: .zero, configuration: cfg)
        super.init()
        view.navigationDelegate = self
        view.uiDelegate = self
        view.isOpaque = false
        view.backgroundColor = UIColor(red: 0.04, green: 0.055, blue: 0.067, alpha: 1)
        view.scrollView.backgroundColor = view.backgroundColor
        let refresh = UIRefreshControl()
        refresh.addTarget(self, action: #selector(reload(_:)), for: .valueChanged)
        view.scrollView.refreshControl = refresh
    }

    @objc private func reload(_ sender: UIRefreshControl) { view.reload(); sender.endRefreshing() }

    func load(_ url: String) {
        failed = false
        guard let u = URL(string: url) else { failed = true; return }
        view.load(URLRequest(url: u, timeoutInterval: 8))
    }

    /// Opens /admin/login?code=… in the web view: the server answers with the session cookie and a redirect to /admin.
    func login(base: String, code: String, done: @escaping (Bool, String) -> Void) {
        guard let u = URL(string: "\(base)/admin/login?code=\(code)") else { done(false, "כתובת לא תקינה"); return }
        loginDone = done
        view.load(URLRequest(url: u, timeoutInterval: 8))
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let r = navigationResponse.response as? HTTPURLResponse, let path = r.url?.path {
            if let done = loginDone, path.hasPrefix("/admin") {
                if r.statusCode == 200 && path == "/admin" { loginDone = nil; done(true, "") }
                else if r.statusCode == 401 { loginDone = nil; done(false, "הקוד לא תקף או שפג תוקפו") }
                else if r.statusCode == 429 { loginDone = nil; done(false, "יותר מדי ניסיונות. לחכות כמה דקות") }
            } else if r.statusCode == 401 && path == "/admin" {
                DispatchQueue.main.async { self.onAuthLost?() }
            }
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if let done = loginDone { loginDone = nil; done(false, "אין חיבור לשרת. בודקים את הכתובת ואת הרשת"); return }
        failed = true
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { failed = false }

    // Links that open a new window (Google sign-in for Gmail / Calendar) go to Safari.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let u = navigationAction.request.url, u.scheme?.hasPrefix("http") == true { UIApplication.shared.open(u) }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (Bool) -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "ביטול", style: .cancel) { _ in completionHandler(false) })
        a.addAction(UIAlertAction(title: "אישור", style: .default) { _ in completionHandler(true) })
        Self.top()?.present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping () -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "אישור", style: .default) { _ in completionHandler() })
        Self.top()?.present(a, animated: true)
    }

    private static func top() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene
        var vc = scene?.keyWindow?.rootViewController
        while let p = vc?.presentedViewController { vc = p }
        return vc
    }
}

struct WebView: UIViewRepresentable {
    let model: WebModel
    func makeUIView(context: Context) -> WKWebView { model.view }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
