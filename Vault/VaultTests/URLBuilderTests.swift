import XCTest
@testable import Vault

final class URLBuilderTests: XCTestCase {
    let base = URL(string: "http://192.168.1.10:8096")!

    func testDirectStreamURL() throws {
        let url = try XCTUnwrap(
            StreamURLBuilder.directStream(baseURL: base, itemId: "abc123", mediaSourceId: "src1")
        )
        XCTAssertEqual(url.path, "/Videos/abc123/stream")
        let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
        let query = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value) })
        XCTAssertEqual(query["static"], "true")
        XCTAssertEqual(query["mediaSourceId"], "src1")
        // Auth must travel as an HTTP header, never inside the URL.
        XCTAssertNil(query["api_key"])
        XCTAssertFalse(url.absoluteString.contains("tok"))
    }

    func testPrimaryImageURL() throws {
        let url = try XCTUnwrap(
            ImageURLBuilder.primary(baseURL: base, itemId: "abc", tag: "t1", maxWidth: 600)
        )
        XCTAssertEqual(url.path, "/Items/abc/Images/Primary")
        XCTAssertTrue(url.query?.contains("maxWidth=600") == true)
        XCTAssertTrue(url.query?.contains("tag=t1") == true)
    }

    func testBackdropImageURLWithoutTag() throws {
        let url = try XCTUnwrap(
            ImageURLBuilder.backdrop(baseURL: base, itemId: "abc", tag: nil, maxWidth: 1920)
        )
        XCTAssertEqual(url.path, "/Items/abc/Images/Backdrop/0")
        XCTAssertFalse(url.query?.contains("tag=") == true)
    }

    func testAuthHeaderWithToken() {
        let header = JellyfinAuthHeader.value(token: "tok123", deviceId: "device-1")
        XCTAssertTrue(header.hasPrefix("MediaBrowser Client=\"Vault\""))
        XCTAssertTrue(header.contains("DeviceId=\"device-1\""))
        XCTAssertTrue(header.contains("Token=\"tok123\""))
    }

    func testAuthHeaderWithoutToken() {
        let header = JellyfinAuthHeader.value(token: nil, deviceId: "device-1")
        XCTAssertFalse(header.contains("Token="))
    }
}
