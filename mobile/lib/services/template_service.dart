import '../config/api_config.dart';
import '../models/task_template.dart';
import 'api_service.dart';

class TemplateService {
  static Future<List<TaskTemplate>> getTemplates() async {
    final data = await ApiService.get(ApiConfig.templates);
    return (data['templates'] as List?)
            ?.map((t) => TaskTemplate.fromJson(t))
            .toList() ??
        [];
  }

  static Future<void> trackUse(int id) async {
    await ApiService.post(ApiConfig.templateUse(id), {});
  }
}
