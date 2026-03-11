import '../config/api_config.dart';
import '../models/task.dart';
import 'api_service.dart';

class TaskService {
  static Future<List<Task>> getTasks({String? status, int limit = 50, int offset = 0}) async {
    final params = <String, String>{'limit': '$limit', 'offset': '$offset'};
    if (status != null) params['status'] = status;
    final data = await ApiService.get(ApiConfig.tasks, params: params);
    final tasks = (data['tasks'] as List?)?.map((t) => Task.fromJson(t)).toList() ?? [];
    return tasks;
  }

  static Future<Task> getTask(int id) async {
    final data = await ApiService.get(ApiConfig.taskById(id));
    return Task.fromJson(data);
  }

  static Future<Task> createTask(Map<String, dynamic> body) async {
    final data = await ApiService.post(ApiConfig.tasks, body);
    return Task.fromJson(data);
  }

  static Future<Task> updateTask(int id, Map<String, dynamic> body) async {
    final data = await ApiService.patch(ApiConfig.taskById(id), body);
    return Task.fromJson(data);
  }

  static Future<void> deleteTask(int id) async {
    await ApiService.delete(ApiConfig.taskById(id));
  }

  static Future<Map<String, dynamic>> getDashboard() async {
    return await ApiService.get(ApiConfig.dashboard);
  }

  static Future<Map<String, dynamic>> getBoard() async {
    return await ApiService.get(ApiConfig.board);
  }
}
