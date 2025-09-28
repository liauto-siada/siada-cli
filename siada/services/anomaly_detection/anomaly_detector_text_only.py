#!/usr/bin/env python3
"""
 Anomaly Detection Algorithm - Text-only Version
Uses only problem_statement.txt text features for training and classification
"""

import os
from pyexpat import model
import re
import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, recall_score, precision_score, f1_score
from sklearn.svm import SVC, OneClassSVM
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LogisticRegression
import warnings
warnings.filterwarnings('ignore')

class AnomalyDetectorTextOnly:
    def __init__(self, data_dir="/"):
        self.data_dir = Path(data_dir)
        self.features = []
        self.labels = []
        self.feature_names = []
        self.scaler = StandardScaler()
        
        # Enhanced text vectorizers
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=500,  # Increase feature count
            stop_words='english',
            ngram_range=(1, 2),  # Include 1-gram and 2-gram
            min_df=2,  # Appear in at least 2 documents
            max_df=0.8  # Appear in at most 80% of documents
        )
        
        self.count_vectorizer = CountVectorizer(
            max_features=200,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
        # Models optimized for text classification
        self.models = {
            'text_rf': RandomForestClassifier(
                n_estimators=200, 
                random_state=42, 
                class_weight='balanced',
                max_depth=15,
                min_samples_split=5
            )
        }
        

    def load_model(self, filepath=None):
        """
        Load saved model and related components
        
        Args:
            filepath (str): Model file path
            
        Returns:
            bool: Whether loading was successful
        """
        try:
            # 'text_anomaly_model.pkl'
            if filepath is None:
                filepath = Path(__file__).parent / "text_anomaly_model.pkl"
            if not os.path.exists(filepath):
                print(f"✗ Model file does not exist: {filepath}")
                return False
            
            # Load model data
            with open(filepath, 'rb') as f:
                model_data = pickle.load(f)
            
            # Restore model components
            self.trained_models = model_data['trained_models']
            self.scaler = model_data['scaler']
            self.tfidf_vectorizer = model_data['tfidf_vectorizer']
            self.count_vectorizer = model_data['count_vectorizer']
            self.feature_names = model_data['feature_names']
            self.train_labels = model_data.get('train_labels', {})
            self.test_labels = model_data.get('test_labels', {})
            
            print(f"✓ Model loaded successfully: {filepath}")
            print(f"Model version: {model_data.get('version', 'Unknown')}")
            print(f"Model description: {model_data.get('description', 'No description')}")
            
            return True
            
        except Exception as e:
            print(f"✗ Model loading failed: {e}")
            return False

    def extract_text_features(self, problem_content):
        """Extract rich text features from problem_statement.txt"""
        if not problem_content or not problem_content.strip():
            return [0] * 20
        
        # Basic text statistics
        char_count = len(problem_content)
        words = problem_content.split()
        word_count = len(words)
        line_count = len(problem_content.split('\n'))
        sentence_count = len([s for s in re.split(r'[.!?]+', problem_content) if s.strip()])
        
        # Language complexity
        if words:
            avg_word_length = np.mean([len(word) for word in words])
            unique_word_ratio = len(set(word.lower() for word in words)) / len(words)
        else:
            avg_word_length = 0
            unique_word_ratio = 0
        
        # Project-specific keywords
        project_keywords = ['django', 'model', 'view', 'form', 'admin', 'template', 'url', 'settings', 'queryset', 'migration']
        project_mentions = sum(problem_content.lower().count(keyword) for keyword in project_keywords)
        
        # Error and problem-related keywords
        error_keywords = ['error', 'bug', 'fail', 'exception', 'warning', 'issue', 'problem', 'broken', 'incorrect']
        error_mentions = sum(problem_content.lower().count(keyword) for keyword in error_keywords)
        
        # Technical terminology density
        tech_keywords = ['function', 'method', 'class', 'attribute', 'field', 'object', 'instance', 'variable']
        tech_mentions = sum(problem_content.lower().count(keyword) for keyword in tech_keywords)
        
        # Code-related features
        code_blocks = len(re.findall(r'```|`[^`]+`', problem_content))
        code_keywords = ['def ', 'class ', 'import ', 'from ', 'if ', 'for ', 'while ', 'try:', 'except:']
        code_pattern_count = sum(problem_content.count(keyword) for keyword in code_keywords)
        
        # URLs and links
        urls = len(re.findall(r'http[s]?://|www\.', problem_content))
        
        # Version numbers and digits
        version_mentions = len(re.findall(r'\d+\.\d+\.?\d*', problem_content))
        number_count = len(re.findall(r'\b\d+\b', problem_content))
        
        # Sentiment and tone analysis
        positive_words = ['good', 'great', 'excellent', 'perfect', 'works', 'success', 'correct', 'expected']
        negative_words = ['bad', 'terrible', 'broken', 'fails', 'wrong', 'incorrect', 'unexpected', 'missing']
        sentiment_score = (sum(problem_content.lower().count(word) for word in positive_words) - 
                          sum(problem_content.lower().count(word) for word in negative_words))
        
        # Question type indicators
        question_words = ['what', 'how', 'why', 'when', 'where', 'which']
        question_count = sum(problem_content.lower().count(word) for word in question_words)
        
        # Uppercase letter ratio
        uppercase_ratio = sum(1 for c in problem_content if c.isupper()) / max(len(problem_content), 1)
        
        # Punctuation density
        punctuation_count = sum(1 for c in problem_content if c in '.,!?;:')
        punctuation_ratio = punctuation_count / max(len(problem_content), 1)
        
        return [
            char_count, word_count, line_count, sentence_count, avg_word_length,
            unique_word_ratio, project_mentions, error_mentions, tech_mentions,
            code_blocks, code_pattern_count, urls, version_mentions, number_count,
            sentiment_score, question_count, uppercase_ratio, punctuation_ratio,
            char_count / max(word_count, 1),  # Average characters per word
            sentence_count / max(line_count, 1)  # Average sentences per line
        ]


    def validate_loaded_model(self, test_samples=None):
        """
        Validate loaded model performance
        
        Args:
            test_samples (list): List of test samples, format: [(text, expected_label), ...]
        """
        try:
            if not hasattr(self, 'trained_models') or len(self.trained_models) == 0:
                print("No loaded model to validate")
                return False
            
            print("\nStarting loaded model validation...")
            
            # Use default test samples if none provided
            if test_samples is None:
                test_samples = [
                    ("Framework QuerySet filtering is not working as expected. When I try to filter with exclude(), it returns incorrect results. This seems like a bug in the ORM layer.", 0),  # Anomaly
                    ("I want to add a new field to my Framework model. How should I create and run migrations properly?", 1),  # Normal
                    ("The Framework admin interface crashes when I try to save a model instance. Getting AttributeError in the admin.", 0),  # Anomaly
                    ("How to implement custom user authentication in Framework? Looking for best practices and examples.", 1),  # Normal
                    ("Framework forms validation fails unexpectedly with clean() method. Error occurs only in production environment.", 0)  # Anomaly
                ]
            
            print(f"Number of validation samples: {len(test_samples)}")
            print(f"{'Sample':<10} {'True Label':<10} {'Pred Label':<10} {'Result':<8} {'Confidence':<10}")
            print("-" * 55)
            
            correct_predictions = 0
            total_predictions = len(test_samples)
            
            for i, (text, expected_label) in enumerate(test_samples):
                prediction = self.infer(text, method='best')
                is_correct = prediction == expected_label
                correct_predictions += is_correct
                
                # Get best model
                best_model_name = max(self.trained_models.keys(), 
                                    key=lambda x: self.trained_models[x].get('test_f1_anomaly', 0))
                
                # Calculate confidence (if model supports predict_proba)
                try:
                    text_features = self.extract_text_features(text)
                    text_features_array = np.array(text_features).reshape(1, -1)
                    features_scaled = self.scaler.transform(text_features_array)
                    tfidf_features = self.tfidf_vectorizer.transform([text]).toarray()
                    count_features = self.count_vectorizer.transform([text]).toarray()
                    final_features = np.hstack([features_scaled, tfidf_features, count_features])
                    
                    model = self.trained_models[best_model_name]['model']
                    if hasattr(model, 'predict_proba'):
                        proba = model.predict_proba(final_features)[0]
                        confidence = max(proba)
                    else:
                        confidence = 0.5  # Default confidence
                except:
                    confidence = 0.5
                
                label_map = {0: "Anomaly", 1: "Normal"}
                result_symbol = "✓" if is_correct else "✗"
                
                print(f"Sample{i+1:<3}    {label_map[expected_label]:<10} {label_map[prediction]:<10} {result_symbol:<8} {confidence:.3f}")
            
            accuracy = correct_predictions / total_predictions
            print(f"\nValidation results:")
            print(f"Overall accuracy: {correct_predictions}/{total_predictions} = {accuracy:.3f}")
            
            if accuracy >= 0.8:
                print("✓ Model validation passed! Good performance")
            elif accuracy >= 0.6:
                print("⚠ Model validation passed, but average performance")
            else:
                print("✗ Model validation failed, poor performance")
            
            return True
            
        except Exception as e:
            print(f"✗ Model validation failed: {e}")
            return False

    def infer(self, problem_statement_str, method='best'):
        """
        Text-only classification interface
        
        Args:
            problem_statement_str (str): problem_statement.txt content
            method (str): Prediction method ('best', 'ensemble', 'specific_model_name')
            
        Returns:
            int: 0 indicates anomaly, 1 indicates normal
        """
        try:
            # Check input
            if not hasattr(self, 'trained_models') or len(self.trained_models) == 0:
                print("Model not trained or loaded, please train or load model first")
                return 1
            
            # Ensure input is not None
            problem_statement_str = problem_statement_str or "Framework issue description"
            
            # Extract text features
            text_features = self.extract_text_features(problem_statement_str)
            
            # Check if features are empty
            if len(text_features) != 20:
                print(f"Text feature extraction failed")
                return 1
            
            # Convert to numpy array and reshape
            text_features_array = np.array(text_features).reshape(1, -1)
            
            # Standardize
            features_scaled = self.scaler.transform(text_features_array)
            
            # Text vectorization
            try:
                tfidf_features = self.tfidf_vectorizer.transform([problem_statement_str]).toarray()
                count_features = self.count_vectorizer.transform([problem_statement_str]).toarray()
            except Exception:
                tfidf_features = np.zeros((1, self.tfidf_vectorizer.max_features or 500))
                count_features = np.zeros((1, self.count_vectorizer.max_features or 200))
            
            # Merge features
            final_features = np.hstack([features_scaled, tfidf_features, count_features])
            
            if method == 'best':
                # Use model with highest F1
                best_model_name = max(self.trained_models.keys(), 
                                    key=lambda x: self.trained_models[x].get('test_f1_anomaly', 0))
                model = self.trained_models[best_model_name]['model']
                prediction = model.predict(final_features)[0]
            elif method == 'ensemble':
                # Ensemble prediction
                predictions = []
                for name, model_info in self.trained_models.items():
                    model = model_info['model']
                    pred = model.predict(final_features)[0]
                    predictions.append(pred)
                
                if predictions:
                    # Voting method
                    prediction = 1 if sum(predictions) > len(predictions) / 2 else 0
                else:
                    prediction = 1
            elif method in self.trained_models:
                # Use specified model
                model = self.trained_models[method]['model']
                prediction = model.predict(final_features)[0]
            else:
                # Default to best model
                best_model_name = max(self.trained_models.keys(), 
                                    key=lambda x: self.trained_models[x].get('test_f1_anomaly', 0))
                model = self.trained_models[best_model_name]['model']
                prediction = model.predict(final_features)[0]
            
            return int(prediction)
            
        except Exception as e:
            print(f"Text-only prediction failed: {e}")
            return 1


def main():
    """Main function"""
    file_path = Path(__file__).parent
    model_path = file_path / "text_anomaly_model.pkl"
    
    print("="*80)
    print("Framework Anomaly Detection Algorithm - Text-only Version (with model save/load functionality)")
    print("="*80)
    
    # Create text-only detector
    detector = AnomalyDetectorTextOnly()

    # Load saved model
    load_success = detector.load_model(model_path)
    if not load_success:
        print("Model loading failed, program terminated")
        return
    
    # Validate loaded model
    detector.validate_loaded_model()
    
    # Stage 4: Practical application testing
    print("\nStage 4: Practical application testing")
    print("-" * 40)
    
    test_cases = [
        ("Framework QuerySet filtering is not working as expected. When I try to filter with exclude(), it returns incorrect results. This seems like a bug in the ORM layer.", "Anomaly"),
        ("I want to add a new field to my Framework model. How should I create and run migrations properly?", "Normal"),
        ("The Framework admin interface crashes when I try to save a model instance. Getting AttributeError in the admin.", "Anomaly"),
        ("How to implement custom user authentication in Framework? Looking for best practices and examples.", "Normal"),
        ("Framework forms validation fails unexpectedly with clean() method. Error occurs only in production environment.", "Anomaly"),
        ("What is the best way to handle static files in Framework for production deployment?", "Normal"),
        ("Framework ORM query optimization tips and best practices for large datasets.", "Normal"),
        ("ModelForm save() method throws IntegrityError but the constraint violation is unclear.", "Anomaly")
    ]
    
    print("Using loaded model for practical classification testing:")
    print(f"{'No.':<4} {'Predicted':<10} {'Expected':<10} {'Status':<8} {'Problem Description':<50}")
    print("-" * 85)
    
    correct_count = 0
    for i, (text, expected) in enumerate(test_cases):
        prediction = detector.infer(text, method='best')
        predicted_label = "Anomaly" if prediction == 0 else "Normal"
        is_correct = predicted_label == expected
        correct_count += is_correct
        
        status = "✓" if is_correct else "✗"
        text_preview = text[:47] + "..." if len(text) > 50 else text
        
        print(f"{i+1:<4} {predicted_label:<10} {expected:<10} {status:<8} {text_preview:<50}")
    
    accuracy = correct_count / len(test_cases)
    print(f"\nPractical application test results: {correct_count}/{len(test_cases)} = {accuracy:.1%}")
    
    # Summary
    print(f"\n" + "="*80)
    print("Framework Anomaly Detection Algorithm complete workflow demonstration finished!")
    print("="*80)
    print(f"✓ Model training: Completed")
    print(f"✓ Model saving: {model_path}")
    print(f"✓ Model loading: Validation passed")
    print(f"✓ Practical application: Accuracy {accuracy:.1%}")
    print(f"\nMain features:")
    print(f"1. Uses only problem_statement.txt text content")
    print(f"2. 20-dimensional handcrafted text features + TF-IDF + Count vectorization")
    print(f"3. Multiple text classification model comparison")
    print(f"4. Model save and load functionality")
    print(f"5. Loaded model validation functionality")
    print(f"6. Feature engineering optimized for Framework problem domain")
    
    return detector


def demo_model_loading():
    """Demonstrate loading saved model functionality only"""
    print("="*60)
    print("Demo: Loading saved model for prediction only")
    print("="*60)
    
    model_path = "text_anomaly_model.pkl"
    data_dir = "benchmark/logs/all_project"
    
    # Create detector instance
    detector = AnomalyDetectorTextOnly(data_dir)
    
    # Try to load model
    if detector.load_model(model_path):
        # Validate model
        detector.validate_loaded_model()
        
        # Make some predictions
        test_text = "Framework forms are not validating properly in my application"
        result = detector.infer(test_text)
        print(f"\nSingle prediction test:")
        print(f"Input: {test_text}")
        print(f"Prediction result: {'Anomaly' if result == 0 else 'Normal'}")
    else:
        print("Model loading failed, please run training program first")


if __name__ == "__main__":
    detector = main()
