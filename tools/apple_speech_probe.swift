import AVFoundation
import Foundation
import Speech

@main
struct AppleSpeechProbe {
    static func main() async {
        let locale = Locale(identifier: CommandLine.arguments.dropFirst().first ?? "en-US")
        let audioPath = CommandLine.arguments.dropFirst(2).first

        if #available(macOS 26.0, *) {
            print("SpeechTranscriber.isAvailable=\(SpeechTranscriber.isAvailable)")
            print("SFSpeechRecognizer.supportedLocales=\(SFSpeechRecognizer.supportedLocales().map(\.identifier).sorted())")
            print("SFSpeechRecognizer(en-US).isAvailable=\(SFSpeechRecognizer(locale: locale)?.isAvailable.description ?? "nil")")
            print("SpeechTranscriber.supportedLocales=\((await SpeechTranscriber.supportedLocales).map(\.identifier).sorted())")
            print("SpeechTranscriber.installedLocales=\((await SpeechTranscriber.installedLocales).map(\.identifier).sorted())")
            print("DictationTranscriber.supportedLocales=\((await DictationTranscriber.supportedLocales).map(\.identifier).sorted())")
            print("DictationTranscriber.installedLocales=\((await DictationTranscriber.installedLocales).map(\.identifier).sorted())")
            print("SpeechTranscriber.supportedLocale=\(String(describing: await SpeechTranscriber.supportedLocale(equivalentTo: locale)))")
            print("DictationTranscriber.supportedLocale=\(String(describing: await DictationTranscriber.supportedLocale(equivalentTo: locale)))")

            await probe("speech.transcription") {
                SpeechTranscriber(locale: locale, preset: .transcription)
            }
            await probe("speech.progressiveTranscription") {
                SpeechTranscriber(locale: locale, preset: .progressiveTranscription)
            }
            await probe("speech.timeIndexedProgressiveTranscription") {
                SpeechTranscriber(locale: locale, preset: .timeIndexedProgressiveTranscription)
            }
            await probe("dictation.shortDictation") {
                DictationTranscriber(locale: locale, preset: .shortDictation)
            }
            await probe("dictation.longDictation") {
                DictationTranscriber(locale: locale, preset: .longDictation)
            }
            await probe("dictation.timeIndexedLongDictation") {
                DictationTranscriber(locale: locale, preset: .timeIndexedLongDictation)
            }

            if let audioPath {
                await probeLegacyRecognition(audioURL: URL(fileURLWithPath: audioPath), locale: locale)
            }
        } else {
            print("requires macOS 26.0 or newer")
        }
    }

    @available(macOS 26.0, *)
    static func probe(_ name: String, makeModule: () -> any SpeechModule) async {
        let module = makeModule()
        let modules: [any SpeechModule] = [module]
        let status = await AssetInventory.status(forModules: modules)
        print("\(name): status=\(status)")
        do {
            _ = try await SpeechAnalyzer(modules: modules)
            print("\(name): analyzer=ok")
        } catch {
            print("\(name): analyzer=ERROR \(error)")
        }
    }

    static func probeLegacyRecognition(audioURL: URL, locale: Locale) async {
        print("legacy.audio=\(audioURL.path)")
        guard let recognizer = SFSpeechRecognizer(locale: locale) else {
            print("legacy.error=missing recognizer")
            return
        }

        let status = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status)
            }
        }
        print("legacy.authorization=\(status.rawValue)")
        guard status == .authorized else {
            return
        }

        let request = SFSpeechURLRecognitionRequest(url: audioURL)
        request.shouldReportPartialResults = false
        if #available(macOS 10.15, *) {
            request.requiresOnDeviceRecognition = false
        }

        await withCheckedContinuation { continuation in
            var resumed = false
            let task = recognizer.recognitionTask(with: request) { result, error in
                if let result {
                    print("legacy.final=\(result.isFinal)")
                    print("legacy.text=\(result.bestTranscription.formattedString)")
                    print("legacy.segments=\(result.bestTranscription.segments.count)")
                }
                if error != nil || result?.isFinal == true {
                    if let error {
                        print("legacy.error=\(error)")
                    }
                    if !resumed {
                        resumed = true
                        continuation.resume()
                    }
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
                if !resumed {
                    task.cancel()
                    resumed = true
                    print("legacy.timeout=30s")
                    continuation.resume()
                }
            }
        }
    }
}
