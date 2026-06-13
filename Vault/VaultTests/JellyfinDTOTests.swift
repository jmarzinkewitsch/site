import XCTest
@testable import Vault

final class JellyfinDTOTests: XCTestCase {
    func testDecodeVaultLibraryItems() throws {
        let json = """
        {
          "Items": [
            {
              "id": "abc123",
              "type": "Movie",
              "title": "Dune: Part Two",
              "overview": "Paul Atreides unites with the Fremen.",
              "year": 2024,
              "genres": ["Science Fiction"],
              "runtime_seconds": 9960,
              "community_rating": 8.6,
              "official_rating": "FSK-12",
              "poster_url": "http://vault.local/poster.jpg",
              "backdrop_url": "http://vault.local/backdrop.jpg",
              "played": false,
              "played_percentage": 36.1,
              "resume_position_seconds": 3600
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
        XCTAssertEqual(item.resumePositionSeconds, 3600, accuracy: 0.01)
        XCTAssertEqual(item.durationSeconds ?? 0, 9960, accuracy: 0.01)
        XCTAssertEqual(item.posterURL?.absoluteString, "http://vault.local/poster.jpg")
        XCTAssertEqual(item.playedPercentage, 36.1)
    }

    func testDecodeVaultEpisode() throws {
        let json = """
        {
          "id": "ep1",
          "title": "Drinking Games",
          "type": "Episode",
          "series_id": "series1",
          "series_name": "Slow Horses",
          "season_id": "season2",
          "index_number": 3,
          "parent_index_number": 2,
          "episode_code": "S2 E3",
          "played": false,
          "resume_position_seconds": 0
        }
        """
        let item = try JSONDecoder().decode(BaseItemDto.self, from: Data(json.utf8))
        XCTAssertEqual(item.kind, .episode)
        XCTAssertEqual(item.episodeCode, "S2 E3")
        XCTAssertEqual(item.seriesName, "Slow Horses")
    }

    func testTicksConversion() {
        XCTAssertEqual(JellyfinTicks.from(seconds: 1.5), 15_000_000)
        XCTAssertEqual(JellyfinTicks.toSeconds(10_000_000), 1.0, accuracy: 0.0001)
    }
}
