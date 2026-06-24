import Foundation
import Speech

@main
struct AppleSpeechProbe {
    static func main() async {
        let locale = Locale(identifier: CommandLine.arguments.dropFirst().first ?? "en-US")

        if #available(macOS 26.0, *) {
            print("SpeechTranscriber.isAvailable=\(SpeechTranscriber.isAvailable)")
            print("SFSpeechRecognizer.supportedLocales=\(SFSpeechRecognizer.supportedLocales().map(\.identifier).sorted())")
            print("SFSpeechRecognizer(en-US).isAvailable=\(SFSpeechRecognizer(locale: locale)?.isAvailable.description ?? "nil")")
            print("SpeechTranscriber.supportedLocales=\((await SpeechTranscriber.supportedLocales).map(\.identifier).sorted())")
            print("SpeechTranscriber.installedLocales=\((await SpeechTranscriber.installedLocales).map(\.identifier).sorted())")
            print("SpeechTranscriber.supportedLocale=\(String(describing: await SpeechTranscriber.supportedLocale(equivalentTo: locale)))")

            await probe("speech.transcription") {
                SpeechTranscriber(locale: locale, preset: .transcription)
            }
            await probe("speech.progressiveTranscription") {
                SpeechTranscriber(locale: locale, preset: .progressiveTranscription)
            }
            await probe("speech.timeIndexedProgressiveTranscription") {
                SpeechTranscriber(locale: locale, preset: .timeIndexedProgressiveTranscription)
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
        _ = SpeechAnalyzer(modules: modules)
        print("\(name): analyzer=ok")
    }
}
