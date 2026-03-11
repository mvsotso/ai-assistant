import '../config/api_config.dart';
import '../models/category.dart';
import 'api_service.dart';

class CategoryService {
  static Future<List<Category>> getCategories() async {
    final data = await ApiService.get(ApiConfig.categories);
    return (data['categories'] as List?)
            ?.map((c) => Category.fromJson(c))
            .toList() ??
        [];
  }
}
