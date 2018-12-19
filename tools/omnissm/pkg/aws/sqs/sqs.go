// Copyright 2018 Capital One Services, LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package sqs

import (
	"context"
	"encoding/json"
	"strconv"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/sqs"
	"github.com/aws/aws-sdk-go/service/sqs/sqsiface"
	"github.com/pkg/errors"
)

type Config struct {
	*aws.Config

	MessageGroupId string
	QueueName      string
	QueueURL       string
}

type SQS struct {
	sqsiface.SQSAPI

	config *Config
}

func New(config *Config) (*SQS, error) {
	s := &SQS{
		SQSAPI: sqs.New(session.New(config.Config)),
		config: config,
	}
	if s.config.QueueURL == "" {
		resp, err := s.SQSAPI.GetQueueUrlWithContext(context.TODO(), &sqs.GetQueueUrlInput{
			QueueName: aws.String(s.config.QueueName),
		})
		if err != nil {
			return nil, err
		}
		s.config.QueueURL = *resp.QueueUrl
	}
	return s, nil
}

func (s *SQS) Send(ctx context.Context, m json.Marshaler) error {
	data, err := json.Marshal(m)
	if err != nil {
		return errors.Wrap(err, "cannot marshal SQS message")
	}
	_, err = s.SQSAPI.SendMessageWithContext(ctx, &sqs.SendMessageInput{
		MessageBody: aws.String(string(data)),
		QueueUrl:    aws.String(s.config.QueueURL),
	})
	if err != nil {
		return err
	}
	return nil
}

type Message struct {
	MessageId                        string
	MessageGroupId                   string
	MessageDeduplicationId           string
	SentTimestamp                    time.Time
	SenderId                         string
	SequenceNumber                   string
	Body                             string
	ReceiptHandle                    string
	ApproximateReceiveCount          int
	ApproximateFirstReceiveTimestamp time.Time
}

func parseUnixTime(s string) time.Time {
	ms, _ := strconv.ParseInt(s, 10, 64)
	return time.Unix(0, ms*int64(time.Millisecond))
}

func (s *SQS) Receive(ctx context.Context) ([]*Message, error) {
	resp, err := s.SQSAPI.ReceiveMessageWithContext(ctx, &sqs.ReceiveMessageInput{

		AttributeNames:      aws.StringSlice([]string{"All"}),
		QueueUrl:            aws.String(s.config.QueueURL),
		WaitTimeSeconds:     aws.Int64(20),
		MaxNumberOfMessages: aws.Int64(10),
	})
	if err != nil {
		return nil, errors.Wrap(err, "cannot receive SQS message")
	}
	messages := make([]*Message, 0)
	for _, m := range resp.Messages {
		attrs := aws.StringValueMap(m.Attributes)
		msg := &Message{
			MessageId:                        *m.MessageId,
			MessageGroupId:                   attrs["MessageGroupId"],
			MessageDeduplicationId:           attrs["MessageDeduplicationId"],
			SentTimestamp:                    parseUnixTime(attrs["SentTimestamp"]),
			SenderId:                         attrs["SenderId"],
			SequenceNumber:                   attrs["SequenceNumber"],
			Body:                             *m.Body,
			ReceiptHandle:                    *m.ReceiptHandle,
			ApproximateFirstReceiveTimestamp: parseUnixTime(attrs["ApproximateFirstReceiveTimestamp"]),
		}
		msg.ApproximateReceiveCount, _ = strconv.Atoi(attrs["ApproximateReceiveCount"])
		messages = append(messages, msg)
	}
	return messages, nil
}

func (s *SQS) Delete(ctx context.Context, receiptHandle string) error {
	_, err := s.SQSAPI.DeleteMessageWithContext(ctx, &sqs.DeleteMessageInput{
		QueueUrl:      aws.String(s.config.QueueURL),
		ReceiptHandle: aws.String(receiptHandle),
	})
	return errors.Wrap(err, "cannot delete SQS message")
}
