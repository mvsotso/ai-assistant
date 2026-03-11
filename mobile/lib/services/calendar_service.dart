import '../config/api_config.dart';
import 'api_service.dart';

class CalendarService {
  static Future<List<Map<String, dynamic>>> getEvents({String? timeMin, String? timeMax}) async {
    final params = <String, String>{};
    if (timeMin != null) params['time_min'] = timeMin;
    if (timeMax != null) params['time_max'] = timeMax;
    final data = await ApiService.get(ApiConfig.calendarEvents, params: params);
    return List<Map<String, dynamic>>.from(data['events'] ?? []);
  }
}
