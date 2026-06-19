import XCTest
@testable import Vault

final class SubtitleSidecarParserTests: XCTestCase {
    func testParsesSRTBlocks() {
        let srt = """
        1
        00:00:01,000 --> 00:00:03,500
        Hello world

        2
        00:01:02,250 --> 00:01:04,000
        Second line
        spanning two rows
        """
        let cues = SubtitleSidecarParser.parse(srt)
        XCTAssertEqual(cues.count, 2)
        XCTAssertEqual(cues[0].startSeconds, 1.0, accuracy: 0.001)
        XCTAssertEqual(cues[0].endSeconds, 3.5, accuracy: 0.001)
        XCTAssertEqual(cues[0].text, "Hello world")
        XCTAssertEqual(cues[1].startSeconds, 62.25, accuracy: 0.001)
        XCTAssertEqual(cues[1].text, "Second line\nspanning two rows")
    }

    func testParsesWebVTTWithHeaderAndCueSettings() {
        let vtt = """
        WEBVTT

        NOTE this is a comment

        00:00:05.000 --> 00:00:07.000 line:90%
        VTT line
        """
        let cues = SubtitleSidecarParser.parse(vtt)
        XCTAssertEqual(cues.count, 1)
        XCTAssertEqual(cues[0].startSeconds, 5.0, accuracy: 0.001)
        XCTAssertEqual(cues[0].endSeconds, 7.0, accuracy: 0.001)
        XCTAssertEqual(cues[0].text, "VTT line")
    }

    func testStripsHTMLAndAssTags() {
        let srt = """
        1
        00:00:01,000 --> 00:00:02,000
        <i>Italic</i> and {\\an8}positioned
        """
        let cues = SubtitleSidecarParser.parse(srt)
        XCTAssertEqual(cues.first?.text, "Italic and positioned")
    }

    func testHandlesCRLFLineEndings() {
        let srt = "1\r\n00:00:01,000 --> 00:00:02,000\r\nWindows line\r\n"
        let cues = SubtitleSidecarParser.parse(srt)
        XCTAssertEqual(cues.first?.text, "Windows line")
    }

    func testSkipsEmptyAndMalformedBlocks() {
        let srt = """
        1
        not a timing line
        still text

        2
        00:00:01,000 --> 00:00:02,000

        3
        00:00:03,000 --> 00:00:04,000
        Valid
        """
        // Block 1 has no "-->", block 2 has empty text — both dropped.
        let cues = SubtitleSidecarParser.parse(srt)
        XCTAssertEqual(cues.map(\.text), ["Valid"])
    }
}
