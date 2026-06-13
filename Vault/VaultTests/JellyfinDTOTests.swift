import XCTest
@testable import Vault

final class JellyfinDTOTests: XCTestCase {
    func testDecodeItemsQueryResult() throws {
        let json = """
        {
          "Items": [
            {
              "Id": "abc123",
              "Name": "Dune: Part Two",
              "Type": "Movie",
              "Overview": "Paul Atreides unites with the Fremen.",
              "RunTimeTicks": 99600000000,
              "ProductionYear": 2024,
              "Genres": ["Science Fiction"],
              "CommunityRating": 8.6,
              "OfficialRating": "FSK-12",
              "ImageTags": { "Primary": "tag-primary" },
              "BackdropImageTags": ["tag-backdrop"],
              "UserData": {
                "PlaybackPositionTicks": 36000000000,
                "Played": false,
                "PlayedPercentage": 36.1
              },
              "MediaSources": [
                {
                  "Id": "source-1",
                  "Container": "mkv",
                  "RunTimeTicks": 99600000000,
                  "MediaStreams": [
                    { "Codec": "hevc", "Type": "Video", "Width": 3840, "Height": 2160, "VideoRange": "HDR", "Index": 0 },
                    { "Codec": "eac3", "Type": "Audio", "Language": "ger", "Channels": 6, "Index": 1 }
                  ]
                }
              ]
            }
          ],
          "TotalRecordCount": 1
        }
        """
        let result = try JSONDecoder().decode(QueryResult<BaseItemDto>.self, from: Data(json.utf8))
        XCTAssertEqual(result.totalRecordCount, 1)
        let item = try XCTUnwrap(result.items.first)
        XCTAssertEqual(item.id, "abc123")
        XCTAssertEqual(item.kind, .movie)
        XCTAssertEqual(item.productionYear, 2024)
        XCTAssertEqual(item.userData?.playbackPositionTicks, 36_000_000_000)
        XCTAssertEqual(item.resumePositionSeconds, 3600, accuracy: 0.01)
        XCTAssertEqual(item.durationSeconds ?? 0, 9960, accuracy: 0.01)
        let video = item.allMediaStreams.first { $0.type == "Video" }
        XCTAssertEqual(video?.codec, "hevc")
        XCTAssertEqual(video?.height, 2160)
        let audio = item.allMediaStreams.first { $0.type == "Audio" }
        XCTAssertEqual(audio?.channels, 6)
    }

    func testDecodeEpisode() throws {
        let json = """
        {
          "Id": "ep1",
          "Name": "Drinking Games",
          "Type": "Episode",
          "SeriesId": "series1",
          "SeriesName": "Slow Horses",
          "SeasonId": "season2",
          "IndexNumber": 3,
          "ParentIndexNumber": 2
        }
        """
        let item = try JSONDecoder().decode(BaseItemDto.self, from: Data(json.utf8))
        XCTAssertEqual(item.kind, .episode)
        XCTAssertEqual(item.episodeCode, "S2 E3")
        XCTAssertEqual(item.seriesName, "Slow Horses")
    }

    func testDecodeAuthenticationResult() throws {
        let json = """
        {
          "User": { "Id": "user-1", "Name": "jan" },
          "AccessToken": "secret-token",
          "ServerId": "server-1"
        }
        """
        let auth = try JSONDecoder().decode(AuthenticationResult.self, from: Data(json.utf8))
        XCTAssertEqual(auth.user.id, "user-1")
        XCTAssertEqual(auth.accessToken, "secret-token")
    }

    func testTicksConversion() {
        XCTAssertEqual(JellyfinTicks.from(seconds: 1.5), 15_000_000)
        XCTAssertEqual(JellyfinTicks.toSeconds(10_000_000), 1.0, accuracy: 0.0001)
    }
}
