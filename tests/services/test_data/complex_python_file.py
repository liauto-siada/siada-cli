#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复杂的Python测试文件
包含多种定义类型，用于测试AST解析功能
"""

import asyncio
import concurrent.futures
import os
import datetime
from typing import List, Dict, Optional, Union, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass
from contextlib import contextmanager
import aiohttp
from bs4 import BeautifulSoup
import numpy as np


@dataclass
class DataModel:
    """数据模型类"""
    name: str
    value: int
    metadata: Optional[Dict[str, Any]] = None


class BaseProcessor(ABC):
    """抽象基类"""
    
    @abstractmethod
    async def process(self, data: DataModel) -> Dict[str, Any]:
        """抽象方法"""
        pass
    
    @abstractmethod
    def validate(self, data: Any) -> bool:
        """验证方法"""
        pass


class DataAnalyzer:
    """数据分析器类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = self._setup_logger()
        self._cache = {}
    
    def complex_data_processing_method(self, dataset: List[Dict], filters: Dict, 
                                     aggregations: List[str], 
                                     transformations: Optional[Dict] = None) -> Dict:
        """
        复杂的数据处理方法 - 超过40行
        处理大型数据集，包含过滤、聚合、转换等多个步骤
        
        Args:
            dataset: 输入数据集
            filters: 过滤条件
            aggregations: 聚合类型列表
            transformations: 可选的数据转换配置
            
        Returns:
            处理结果字典
        """
        # 数据验证阶段
        if not dataset or not isinstance(dataset, list):
            raise ValueError("Dataset must be a non-empty list")
        
        if not filters or not isinstance(filters, dict):
            raise ValueError("Filters must be a non-empty dictionary")
            
        # 数据预处理阶段
        processed_data = []
        for record in dataset:
            if self._validate_record(record):
                cleaned_record = self._clean_record(record)
                if self._apply_filters(cleaned_record, filters):
                    processed_data.append(cleaned_record)
        
        # 数据转换阶段
        if transformations:
            for transform_key, transform_func in transformations.items():
                for record in processed_data:
                    if transform_key in record:
                        try:
                            record[transform_key] = transform_func(record[transform_key])
                        except Exception as e:
                            self.logger.warning(f"Transform failed for {transform_key}: {e}")
                            
        # 数据聚合阶段
        aggregated_results = {}
        for agg_type in aggregations:
            if agg_type == 'sum':
                aggregated_results['sum'] = self._calculate_sum(processed_data)
            elif agg_type == 'average':
                aggregated_results['average'] = self._calculate_average(processed_data)
            elif agg_type == 'count':
                aggregated_results['count'] = len(processed_data)
            elif agg_type == 'group_by':
                aggregated_results['groups'] = self._group_by_category(processed_data)
            elif agg_type == 'statistical_summary':
                aggregated_results['stats'] = self._generate_statistical_summary(processed_data)
                
        return {
            'processed_count': len(processed_data),
            'original_count': len(dataset),
            'aggregations': aggregated_results,
            'metadata': {
                'filters_applied': filters,
                'transformations_applied': transformations or {},
                'processing_timestamp': datetime.datetime.now().isoformat()
            }
        }
    
    def _validate_record(self, record: Dict) -> bool:
        """验证单条记录"""
        return isinstance(record, dict) and len(record) > 0
    
    def _clean_record(self, record: Dict) -> Dict:
        """清理单条记录"""
        return {k: v for k, v in record.items() if v is not None}
    
    def _apply_filters(self, record: Dict, filters: Dict) -> bool:
        """应用过滤条件"""
        for key, value in filters.items():
            if key not in record or record[key] != value:
                return False
        return True
    
    def _setup_logger(self):
        """设置日志器"""
        import logging
        return logging.getLogger(__name__)


class MLModelTrainer:
    """机器学习模型训练器"""
    
    def __init__(self, model_config: Dict[str, Any]):
        self.model_config = model_config
        self.logger = self._create_logger()
        self.model_save_path = "models/best_model.pkl"
    
    def train_complex_model(self, training_data: np.ndarray, labels: np.ndarray,
                          validation_data: Optional[np.ndarray] = None,
                          validation_labels: Optional[np.ndarray] = None,
                          hyperparameters: Dict = None,
                          callbacks: List = None) -> Dict:
        """
        复杂的机器学习模型训练方法 - 超过50行
        包含数据预处理、模型构建、训练、验证等完整流程
        
        Args:
            training_data: 训练数据
            labels: 训练标签
            validation_data: 验证数据
            validation_labels: 验证标签
            hyperparameters: 超参数配置
            callbacks: 回调函数列表
            
        Returns:
            训练结果字典
        """
        # 参数初始化和验证
        if hyperparameters is None:
            hyperparameters = self._get_default_hyperparameters()
            
        if callbacks is None:
            callbacks = [self._create_early_stopping(), self._create_model_checkpoint()]
            
        self.logger.info(f"Starting model training with {len(training_data)} samples")
        
        # 数据预处理阶段
        X_train_processed = self._preprocess_features(training_data)
        y_train_processed = self._preprocess_labels(labels)
        
        if validation_data is not None:
            X_val_processed = self._preprocess_features(validation_data)
            y_val_processed = self._preprocess_labels(validation_labels)
        else:
            # 自动分割训练集
            split_idx = int(len(X_train_processed) * 0.8)
            X_val_processed = X_train_processed[split_idx:]
            y_val_processed = y_train_processed[split_idx:]
            X_train_processed = X_train_processed[:split_idx]
            y_train_processed = y_train_processed[:split_idx]
            
        # 模型构建阶段
        model = self._build_model(
            input_shape=X_train_processed.shape[1:],
            num_classes=len(np.unique(y_train_processed)),
            **hyperparameters
        )
        
        optimizer = self._create_optimizer(hyperparameters.get('learning_rate', 0.001))
        model.compile(optimizer=optimizer, loss='categorical_crossentropy', metrics=['accuracy'])
        
        # 训练执行阶段
        training_history = {'loss': [], 'accuracy': [], 'val_loss': [], 'val_accuracy': []}
        best_val_accuracy = 0.0
        patience_counter = 0
        
        for epoch in range(hyperparameters.get('epochs', 100)):
            # 训练一个epoch
            epoch_loss, epoch_accuracy = self._train_epoch(
                model, X_train_processed, y_train_processed, 
                batch_size=hyperparameters.get('batch_size', 32)
            )
            
            # 验证
            val_loss, val_accuracy = self._validate_epoch(model, X_val_processed, y_val_processed)
            
            # 记录历史
            training_history['loss'].append(epoch_loss)
            training_history['accuracy'].append(epoch_accuracy)
            training_history['val_loss'].append(val_loss)
            training_history['val_accuracy'].append(val_accuracy)
            
            # 早停检查
            if val_accuracy > best_val_accuracy:
                best_val_accuracy = val_accuracy
                patience_counter = 0
                self._save_best_model(model)
            else:
                patience_counter += 1
                if patience_counter >= hyperparameters.get('patience', 10):
                    self.logger.info(f"Early stopping at epoch {epoch}")
                    break
                    
            # 执行回调
            for callback in callbacks:
                callback.on_epoch_end(epoch, {'val_accuracy': val_accuracy})
                
        return {
            'model': model,
            'training_history': training_history,
            'best_validation_accuracy': best_val_accuracy,
            'total_epochs': epoch + 1,
            'final_model_path': self.model_save_path
        }
    
    @classmethod
    def from_config_file(cls, config_path: str):
        """从配置文件创建实例"""
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)
        return cls(config)
    
    @staticmethod
    def validate_training_data(data: np.ndarray, labels: np.ndarray) -> bool:
        """验证训练数据"""
        return len(data) == len(labels) and len(data) > 0


class WebCrawler:
    """网络爬虫类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = self._setup_logger()
    
    async def crawl_website_comprehensive(self, base_url: str, max_pages: int = 100,
                                        crawl_rules: Dict = None,
                                        rate_limit: float = 1.0,
                                        retry_config: Dict = None) -> Dict:
        """
        全面的网站爬取方法 - 超过60行
        支持多线程、错误重试、内容解析、数据存储等功能
        
        Args:
            base_url: 起始URL
            max_pages: 最大爬取页面数
            crawl_rules: 爬取规则
            rate_limit: 速率限制
            retry_config: 重试配置
            
        Returns:
            爬取结果字典
        """
        # 初始化配置
        if crawl_rules is None:
            crawl_rules = self._get_default_crawl_rules()
            
        if retry_config is None:
            retry_config = {'max_retries': 3, 'backoff_factor': 2}
            
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        crawled_urls = set()
        failed_urls = []
        extracted_data = []
        
        # URL队列初始化
        url_queue = asyncio.Queue()
        await url_queue.put(base_url)
        
        semaphore = asyncio.Semaphore(crawl_rules.get('concurrent_requests', 5))
        
        # 爬取主循环
        while not url_queue.empty() and len(crawled_urls) < max_pages:
            current_url = await url_queue.get()
            
            if current_url in crawled_urls:
                continue
                
            async with semaphore:
                try:
                    # 发送请求
                    async with session.get(current_url) as response:
                        if response.status == 200:
                            content = await response.text()
                            crawled_urls.add(current_url)
                            
                            # 内容解析
                            soup = BeautifulSoup(content, 'html.parser')
                            
                            # 提取数据
                            page_data = {
                                'url': current_url,
                                'title': soup.find('title').text if soup.find('title') else '',
                                'content': self._extract_main_content(soup),
                                'links': self._extract_links(soup, current_url),
                                'images': self._extract_images(soup, current_url),
                                'metadata': self._extract_metadata(soup),
                                'crawl_timestamp': datetime.datetime.now().isoformat()
                            }
                            
                            extracted_data.append(page_data)
                            
                            # 添加新发现的URL到队列
                            for link in page_data['links']:
                                if self._should_crawl_url(link, crawl_rules):
                                    await url_queue.put(link)
                                    
                        else:
                            self.logger.warning(f"Failed to crawl {current_url}: HTTP {response.status}")
                            failed_urls.append({'url': current_url, 'status': response.status})
                            
                except asyncio.TimeoutError:
                    self.logger.error(f"Timeout crawling {current_url}")
                    failed_urls.append({'url': current_url, 'error': 'timeout'})
                    
                except Exception as e:
                    self.logger.error(f"Error crawling {current_url}: {str(e)}")
                    failed_urls.append({'url': current_url, 'error': str(e)})
                    
                # 速率限制
                await asyncio.sleep(rate_limit)
                
        await session.close()
        
        # 数据后处理和存储
        processed_data = self._post_process_crawled_data(extracted_data)
        storage_result = await self._store_crawled_data(processed_data)
        
        return {
            'total_pages_crawled': len(crawled_urls),
            'total_data_extracted': len(extracted_data),
            'failed_urls': failed_urls,
            'crawled_urls': list(crawled_urls),
            'extracted_data': processed_data,
            'storage_info': storage_result,
            'crawl_statistics': self._generate_crawl_statistics(extracted_data, failed_urls)
        }


class FileProcessor:
    """文件处理器类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = self._setup_logger()
    
    def process_large_file_batch(self, file_paths: List[str], 
                               processing_config: Dict,
                               output_directory: str,
                               parallel_workers: int = 4) -> Dict:
        """
        批量处理大文件的复杂方法 - 超过45行
        支持多种文件格式、并行处理、进度跟踪、错误恢复
        
        Args:
            file_paths: 文件路径列表
            processing_config: 处理配置
            output_directory: 输出目录
            parallel_workers: 并行工作进程数
            
        Returns:
            处理结果字典
        """
        # 配置验证和初始化
        if not file_paths:
            raise ValueError("File paths list cannot be empty")
            
        if not os.path.exists(output_directory):
            os.makedirs(output_directory, exist_ok=True)
            
        processing_results = []
        failed_files = []
        total_files = len(file_paths)
        
        # 创建进程池
        with concurrent.futures.ProcessPoolExecutor(max_workers=parallel_workers) as executor:
            # 提交所有任务
            future_to_file = {
                executor.submit(self._process_single_file, file_path, processing_config, output_directory): file_path
                for file_path in file_paths
            }
            
            # 处理完成的任务
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                completed_count += 1
                
                try:
                    result = future.result(timeout=300)  # 5分钟超时
                    processing_results.append({
                        'file_path': file_path,
                        'status': 'success',
                        'output_path': result['output_path'],
                        'processing_time': result['processing_time'],
                        'file_size_before': result['file_size_before'],
                        'file_size_after': result['file_size_after'],
                        'metadata': result.get('metadata', {})
                    })
                    
                    # 进度报告
                    progress = (completed_count / total_files) * 100
                    self.logger.info(f"Progress: {progress:.1f}% ({completed_count}/{total_files})")
                    
                except concurrent.futures.TimeoutError:
                    self.logger.error(f"Timeout processing file: {file_path}")
                    failed_files.append({
                        'file_path': file_path,
                        'error': 'Processing timeout',
                        'error_type': 'timeout'
                    })
                    
                except Exception as e:
                    self.logger.error(f"Error processing file {file_path}: {str(e)}")
                    failed_files.append({
                        'file_path': file_path,
                        'error': str(e),
                        'error_type': type(e).__name__
                    })
                    
        # 生成处理报告
        successful_files = [r for r in processing_results if r['status'] == 'success']
        total_size_before = sum(r['file_size_before'] for r in successful_files)
        total_size_after = sum(r['file_size_after'] for r in successful_files)
        total_processing_time = sum(r['processing_time'] for r in successful_files)
        
        return {
            'total_files_processed': len(successful_files),
            'total_files_failed': len(failed_files),
            'success_rate': len(successful_files) / total_files * 100,
            'total_size_reduction': total_size_before - total_size_after,
            'total_processing_time': total_processing_time,
            'average_processing_time': total_processing_time / len(successful_files) if successful_files else 0,
            'successful_files': successful_files,
            'failed_files': failed_files,
            'output_directory': output_directory
        }
    
    @contextmanager
    def file_processing_context(self, temp_dir: str):
        """文件处理上下文管理器"""
        try:
            os.makedirs(temp_dir, exist_ok=True)
            yield temp_dir
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


def generator_function(items: List[Any]):
    """生成器函数"""
    for item in items:
        yield item * 2


async def async_main():
    """异步主函数"""
    analyzer = DataAnalyzer({"debug": True})
    data = [{"name": "test", "value": 42}]
    result = analyzer.complex_data_processing_method(
        data, {"name": "test"}, ["count", "sum"]
    )
    return result


def utility_function(x: int, y: int = 10) -> int:
    """工具函数"""
    def inner_function(a: int) -> int:
        """内嵌函数"""
        return a * 2
    
    return inner_function(x) + y


# 全局变量
GLOBAL_CONFIG = {
    "version": "1.0.0",
    "debug": False
}


if __name__ == "__main__":
    # 主程序入口
    result = asyncio.run(async_main())
    print(f"Result: {result}")
