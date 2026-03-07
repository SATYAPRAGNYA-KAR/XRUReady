import Foundation

class APIClient {

    static func requestDiagnosis(symptoms: [String], completion: @escaping (DiagnosisResponse) -> Void) {

        let url = URL(string: "http://SERVER_IP:8000/diagnose")!

        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let body: [String: Any] = [
            "symptoms": symptoms
        ]

        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request) { data, _, _ in

            if let data = data {
                let response = try! JSONDecoder().decode(DiagnosisResponse.self, from: data)
                completion(response)
            }

        }.resume()
    }
}