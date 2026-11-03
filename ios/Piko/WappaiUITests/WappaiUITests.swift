import XCTest

final class WappaiUITests:XCTestCase {
    var app:XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure=false
        app=XCUIApplication();app.launchArguments=["--qa-ui-fixture","--qa-ui-reset"]
        app.launch();XCTAssertTrue(pip.waitForExistence(timeout:15))
    }
    var pip:XCUIElement {app.descendants(matching:.any)["floatingPip"].firstMatch}
    func testFloatingPipDragPersistsAndStaysInsideScreen() {
        let original=pip.frame;XCTAssertGreaterThan(original.midX,app.frame.midX)
        let target=app.coordinate(withNormalizedOffset:CGVector(dx:0.25,dy:0.45))
        pip.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).press(forDuration:0.7,thenDragTo:target)
        let moved=pip.frame;XCTAssertLessThan(moved.midX,original.midX-70);XCTAssertLessThan(moved.midY,original.midY-100)
        app.terminate();app.launchArguments=["--qa-ui-fixture"];app.launch();XCTAssertTrue(pip.waitForExistence(timeout:10))
        XCTAssertEqual(pip.frame.midX,moved.midX,accuracy:15);XCTAssertEqual(pip.frame.midY,moved.midY,accuracy:15)
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertTrue(app.frame.insetBy(dx:-1,dy:-1).contains(pip.frame))
        XCUIDevice.shared.orientation = .portrait
    }
    func testLongPressHideAndRestore() {
        pip.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).press(forDuration:0.7)
        let hide=app.buttons["הסתרת הדמות"];XCTAssertTrue(hide.waitForExistence(timeout:5));hide.tap()
        XCTAssertTrue(pip.waitForNonExistence(timeout:5),app.debugDescription)
        app.buttons["הגדרות"].tap()
        let show=app.switches["הצגת הדמות הצפה"]
        if !show.isHittable {app.swipeUp()};XCTAssertTrue(show.waitForExistence(timeout:5))
        XCTAssertEqual(show.value as? String,"0")
        show.coordinate(withNormalizedOffset:CGVector(dx:0.1,dy:0.5)).tap()
        let enabled=XCTNSPredicateExpectation(predicate:NSPredicate(format:"value == %@","1"),object:show)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:5),.completed,show.debugDescription)
        app.buttons["סיום"].tap();XCTAssertTrue(pip.waitForExistence(timeout:5),app.debugDescription)
    }
    func testTapGalleryAndProtectedBuiltins() {
        pip.tap();XCTAssertTrue(app.navigationBars["Pips"].waitForExistence(timeout:5))
        app.buttons["pipOptions-pip"].tap()
        XCTAssertTrue(app.buttons["הבעות וצלילים"].waitForExistence(timeout:5))
        XCTAssertFalse(app.buttons["עריכת הדמות"].exists);XCTAssertFalse(app.buttons["מחיקה"].exists)
    }
    func testNewCharacterNeedsNameAndBriefOrImage() {
        pip.tap();app.buttons["יצירת Pip חדש"].tap()
        let create=app.buttons["יצירת תצוגה מקדימה"];XCTAssertTrue(create.waitForExistence(timeout:5));XCTAssertFalse(create.isEnabled)
        let name=app.textFields["שם הדמות"];name.tap();name.typeText("Lumi")
        XCTAssertFalse(create.isEnabled)
        let brief=app.descendants(matching:.any)["pipDescription"].firstMatch;XCTAssertTrue(brief.exists);brief.tap();brief.typeText("A friendly purple bird")
        XCTAssertTrue(create.isEnabled);XCTAssertTrue(app.buttons["תמונה מהספרייה"].exists);XCTAssertTrue(app.buttons["תמונה מקובץ"].exists)
    }
    func testHebrewDrawerOpensFromRightEdge() {
        let start=app.coordinate(withNormalizedOffset:CGVector(dx:0.995,dy:0.4))
        let end=app.coordinate(withNormalizedOffset:CGVector(dx:0.3,dy:0.4))
        start.press(forDuration:0.1,thenDragTo:end)
        XCTAssertTrue(app.buttons["שיחה חדשה"].waitForExistence(timeout:5))
    }
    func testVoiceSetupAndLiveTranscriptSetting() {
        app.buttons["הגדרות"].tap()
        for _ in 0..<4 {if app.switches["תמלול בזמן הדיבור"].exists{break};app.swipeUp()}
        XCTAssertTrue(app.switches["תמלול בזמן הדיבור"].waitForExistence(timeout:5))
        app.buttons["קול ודיבור"].tap()
        let provider=app.buttons["voiceProvider"]
        XCTAssertTrue(provider.waitForExistence(timeout:5));provider.tap()
        app.buttons["ElevenLabs"].tap()
        XCTAssertTrue(app.secureTextFields["מפתח API"].waitForExistence(timeout:5))
        XCTAssertFalse(app.buttons["שמירת הקול והסגנון"].isEnabled)
        let screenshot=XCTAttachment(screenshot:app.screenshot());screenshot.name="ElevenLabs setup";screenshot.lifetime = .keepAlways;add(screenshot)
    }

    func testFirmwareUpdateCheckUsesCurrentBoardAndDoesNotInstall() {
        app.buttons["הגדרות"].tap()
        let check=app.buttons["checkFirmwareUpdates"]
        XCTAssertTrue(check.waitForExistence(timeout:10))
        check.tap()
        let status=app.staticTexts["firmwareUpdateStatus"]
        XCTAssertTrue(status.waitForExistence(timeout:5))
        XCTAssertTrue(status.label.contains("בדיקת ממשק מקומית"))
        XCTAssertFalse(app.buttons["התקנת העדכון באמצעות מחשב ו־USB"].exists)
        let screenshot=XCTAttachment(screenshot:app.screenshot());screenshot.name="Firmware update settings";screenshot.lifetime = .keepAlways;add(screenshot)
    }


    func testMeetingLibraryAndTranscript() throws {
        let app=XCUIApplication()
        app.launchArguments=["--qa-ui-fixture","--qa-ui-reset","--show-meetings"]
        app.launch()
        XCTAssertTrue(app.staticTexts["תכנון ההשקה"].waitForExistence(timeout:10))
        let library=XCTAttachment(screenshot:app.screenshot());library.name="Meeting library";library.lifetime = .keepAlways;add(library)
        app.staticTexts["תכנון ההשקה"].tap()
        XCTAssertTrue(app.staticTexts["תמלול"].waitForExistence(timeout:5))
        let detail=XCTAttachment(screenshot:app.screenshot());detail.name="Meeting transcript";detail.lifetime = .keepAlways;add(detail)
    }

    func testSidebarDeleteRequiresConfirmationAndKeepsUsableChat() {
        let start=app.coordinate(withNormalizedOffset:CGVector(dx:0.995,dy:0.4))
        start.press(forDuration:0.1,thenDragTo:app.coordinate(withNormalizedOffset:CGVector(dx:0.3,dy:0.4)))
        let options=app.buttons["sessionOptions-ui-qa"]
        XCTAssertTrue(options.waitForExistence(timeout:5));options.tap()
        app.buttons["מחיקת השיחה"].tap()
        XCTAssertTrue(app.alerts["למחוק את השיחה?"].waitForExistence(timeout:5))
        app.alerts.buttons["ביטול"].tap();XCTAssertTrue(options.exists)
        options.tap();app.buttons["מחיקת השיחה"].tap();app.alerts.buttons["מחיקה"].tap()
        XCTAssertTrue(options.waitForNonExistence(timeout:5))
        XCTAssertTrue(app.buttons["שיחה חדשה"].exists)
        XCTAssertFalse(app.staticTexts["בדיקת ממשק"].exists)
        let screenshot=XCTAttachment(screenshot:app.screenshot());screenshot.name="Sidebar after confirmed deletion";screenshot.lifetime = .keepAlways;add(screenshot)
    }

    // Seed the isolated simulator Photos library with server/sim/pixel-0-0.png.
    func testImageCharacterNeedsOnlyImageConfirmation() {
        pip.tap();app.buttons["יצירת Pip חדש"].tap()
        app.buttons["תמונה מהספרייה"].tap()
        let photo=app.images.matching(identifier:"PXGGridLayout-Info").firstMatch
        XCTAssertTrue(photo.waitForExistence(timeout:8),app.debugDescription)
        photo.tap()
        let confirm=app.buttons["אישור התמונה ויצירת תצוגה מקדימה"]
        XCTAssertTrue(confirm.waitForExistence(timeout:8),app.debugDescription)
        XCTAssertTrue(confirm.isEnabled)
        XCTAssertFalse(app.textFields["שם הדמות"].exists)
        XCTAssertFalse(app.descendants(matching:.any)["pipDescription"].firstMatch.exists)
        XCTAssertFalse(app.buttons["אישור ויצירה מלאה"].exists)
        let screenshot=XCTAttachment(screenshot:app.screenshot());screenshot.name="Image confirmation without brief";screenshot.lifetime = .keepAlways;add(screenshot)
        app.buttons["הסרת התמונה"].tap()
        XCTAssertTrue(app.textFields["שם הדמות"].waitForExistence(timeout:5))
        XCTAssertFalse(app.buttons["יצירת תצוגה מקדימה"].isEnabled)
    }
}
