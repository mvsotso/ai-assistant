import '../config/api_config.dart';
import '../models/task_group.dart';
import 'api_service.dart';

class GroupService {
  static Future<List<TaskGroup>> getGroups() async {
    final data = await ApiService.get(ApiConfig.taskGroups);
    return (data['groups'] as List?)
            ?.map((g) => TaskGroup.fromJson(g))
            .toList() ??
        [];
  }
}
