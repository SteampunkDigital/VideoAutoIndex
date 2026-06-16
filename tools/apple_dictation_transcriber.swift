import AVFoundation
import CoreMedia
import Foundation
import Speech

struct TranscriptChunk: Codable {
    let timestamp: [Double]
    let text: String
}

struct Transcript: Codable {
    let speakers: [String]
    let chunks: [TranscriptChunk]
    let text: String
}

enum ToolError: Error, CustomStringConvertible {
    case missingArgument(String)
    case unsupportedRuntime
    case invalidAudioPath(String)

    var description: String {
        switch self {
        case .missingArgument(let message):
            return message
        case .unsupportedRuntime:
            return "Apple DictationTranscriber requires macOS 26.0 or newer."
        case .invalidAudioPath(let path):
            return "Audio file not found: \(path)"
        }
    }
}

@main
struct AppleDictationTranscriberTool {
    static func main() async {
        do {
            try await run()
        } catch {
            fputs("Error: \(error)\n", stderr)
            exit(1)
        }
    }

    static func run() async throws {
        let args = parseArguments(CommandLine.arguments.dropFirst())
        guard let audioPath = args["audio"] else {
            throw ToolError.missingArgument("Missing required argument: --audio")
        }
        guard let transcriptPath = args["transcript"] else {
            throw ToolError.missingArgument("Missing required argument: --transcript")
        }
        guard let srtPath = args["srt"] else {
            throw ToolError.missingArgument("Missing required argument: --srt")
        }
        let localeIdentifier = args["locale"] ?? "en-US"

        guard FileManager.default.fileExists(atPath: audioPath) else {
            throw ToolError.invalidAudioPath(audioPath)
        }

        if #available(macOS 26.0, *) {
            let chunks = try await transcribe(
                audioURL: URL(fileURLWithPath: audioPath),
                locale: Locale(identifier: localeIdentifier)
            )
            let transcript = Transcript(
                speakers: [],
                chunks: chunks,
                text: chunks.map(\.text).joined(separator: " ")
            )

            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: transcriptPath).deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: srtPath).deletingLastPathComponent(),
                withIntermediateDirectories: true
            )

            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
            try encoder.encode(transcript).write(to: URL(fileURLWithPath: transcriptPath))
            try writeSRT(chunks: chunks, to: URL(fileURLWithPath: srtPath))
        } else {
            throw ToolError.unsupportedRuntime
        }
    }

    static func parseArguments<S: Sequence>(_ arguments: S) -> [String: String] where S.Element == String {
        var parsed: [String: String] = [:]
        var iterator = arguments.makeIterator()
        while let argument = iterator.next() {
            guard argument.hasPrefix("--") else {
                continue
            }
            let key = String(argument.dropFirst(2))
            parsed[key] = iterator.next()
        }
        return parsed
    }

    @available(macOS 26.0, *)
    static func transcribe(audioURL: URL, locale: Locale) async throws -> [TranscriptChunk] {
        let transcriber = DictationTranscriber(locale: locale, preset: .timeIndexedLongDictation)
        let modules: [any SpeechModule] = [transcriber]

        let status = await AssetInventory.status(forModules: modules)
        if status != .installed {
            if let request = try await AssetInventory.assetInstallationRequest(supporting: modules) {
                try await request.downloadAndInstall()
            }
        }

        let audioFile = try AVAudioFile(forReading: audioURL)
        let analyzer = try await SpeechAnalyzer(
            inputAudioFile: audioFile,
            modules: modules,
            finishAfterFile: true
        )

        var resultTaskChunks: [TranscriptChunk] = []
        let resultTask = Task {
            var chunks: [TranscriptChunk] = []
            for try await result in transcriber.results {
                let text = String(result.text.characters)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else {
                    continue
                }

                let start = max(0.0, CMTimeGetSeconds(result.range.start))
                let duration = max(0.0, CMTimeGetSeconds(result.range.duration))
                let end = max(start, start + duration)
                chunks.append(
                    TranscriptChunk(
                        timestamp: [roundToMillis(start), roundToMillis(end)],
                        text: text
                    )
                )
            }
            return chunks
        }

        try await analyzer.start(inputAudioFile: audioFile, finishAfterFile: true)
        resultTaskChunks = try await resultTask.value
        return mergeAdjacentDuplicates(resultTaskChunks)
    }

    static func mergeAdjacentDuplicates(_ chunks: [TranscriptChunk]) -> [TranscriptChunk] {
        var merged: [TranscriptChunk] = []
        for chunk in chunks {
            if merged.last?.text == chunk.text {
                continue
            }
            merged.append(chunk)
        }
        return merged
    }

    static func writeSRT(chunks: [TranscriptChunk], to url: URL) throws {
        var output = ""
        for (index, chunk) in chunks.enumerated() {
            let start = chunk.timestamp.first ?? 0.0
            let end = chunk.timestamp.dropFirst().first ?? start
            output += "\(index + 1)\n"
            output += "\(formatTimestamp(start)) --> \(formatTimestamp(end))\n"
            output += "\(chunk.text)\n\n"
        }
        try output.write(to: url, atomically: true, encoding: .utf8)
    }

    static func roundToMillis(_ value: Double) -> Double {
        (value * 1000.0).rounded() / 1000.0
    }

    static func formatTimestamp(_ seconds: Double) -> String {
        let safeSeconds = max(0.0, seconds)
        let millisecondsTotal = Int((safeSeconds * 1000.0).rounded())
        let hours = millisecondsTotal / 3_600_000
        let minutes = (millisecondsTotal % 3_600_000) / 60_000
        let secs = (millisecondsTotal % 60_000) / 1000
        let millis = millisecondsTotal % 1000
        return String(format: "%02d:%02d:%02d,%03d", hours, minutes, secs, millis)
    }
}
