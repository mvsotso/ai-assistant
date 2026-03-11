import '../config/api_config.dart';
import '../models/team_member.dart';
import 'api_service.dart';

class TeamService {
  static Future<List<TeamMember>> getMembers() async {
    final data = await ApiService.get(ApiConfig.team);
    return (data['members'] as List?)
            ?.map((m) => TeamMember.fromJson(m))
            .toList() ??
        [];
  }
}
