import '../config/api_config.dart';
import 'api_service.dart';

class AIService {
  static Future<Map<String, dynamic>> chat(String message, {List<Map<String, String>>? history}) async {
    return await ApiService.post(ApiConfig.aiChat, {
      'message': message,
      if (history != null) 'history': history,
    });
  }

  static Future<Map<String, dynamic>> prioritize() async {
    return await ApiService.post(ApiConfig.aiPrioritize, {'include_workload': true});
  }
}
