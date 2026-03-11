import '../config/api_config.dart';
import 'api_service.dart';

class ChecklistService {
  static Future<Map<String, dynamic>> getActions(int taskId) async {
    final data = await ApiService.get(ApiConfig.taskActions(taskId));
    return data is Map<String, dynamic> ? data : {};
  }

  static Future<Map<String, dynamic>> createAction(
      int taskId, Map<String, dynamic> body) async {
    return await ApiService.post(ApiConfig.taskActions(taskId), body);
  }

  static Future<Map<String, dynamic>> toggleAction(
      int taskId, int actionId) async {
    return await ApiService.post(
        ApiConfig.taskActionToggle(taskId, actionId), {});
  }

  static Future<void> deleteAction(int taskId, int actionId) async {
    await ApiService.delete(ApiConfig.taskActionById(taskId, actionId));
  }
}
