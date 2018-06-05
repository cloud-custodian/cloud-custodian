package manager

import (
	"encoding/json"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/sqs"
	"github.com/aws/aws-sdk-go/service/sqs/sqsiface"
	"github.com/google/uuid"
	"github.com/pkg/errors"
)

type MessageType int

const (
	CreateActivation MessageType = iota
	AddTagsToResource
	PutInventory
	DeregisterManagedInstance
)

type Message struct {
	MessageId string
	Type      MessageType
	Body      json.RawMessage

	ReceiptHandle string

	DeleteFunc func() error `json:"-"`
}

func NewMessage(t MessageType, v interface{}) (*Message, error) {
	data, err := json.Marshal(v)
	if err != nil {
		return nil, errors.Wrap(err, "cannot create new message")
	}
	return &Message{
		MessageId: uuid.New().String(),
		Type:      t,
		Body:      data,
	}, nil
}

func (m *Message) Delete() error {
	return m.DeleteFunc()
}

type Queue struct {
	sqsiface.SQSAPI

	queueURL string
}

func NewQueue(name string, config *aws.Config) (*Queue, error) {
	sess := session.New(config)
	q := &Queue{
		SQSAPI: sqs.New(sess),
	}
	resp, err := q.SQSAPI.GetQueueUrl(&sqs.GetQueueUrlInput{
		QueueName: aws.String(name),
		//QueueOwnerAWSAccountId: config.AccountId,
	})
	if err != nil {
		return nil, err
	}
	q.queueURL = *resp.QueueUrl
	return q, nil
}

func (q *Queue) Send(m *Message) error {
	data, err := json.Marshal(m)
	if err != nil {
		return errors.Wrap(err, "cannot marshal SQS message")
	}
	_, err = q.SQSAPI.SendMessage(&sqs.SendMessageInput{
		MessageDeduplicationId: aws.String(m.MessageId),
		MessageGroupId:         aws.String("omnissm"),
		MessageBody:            aws.String(string(data)),
		QueueUrl:               aws.String(q.queueURL),
	})
	if err != nil {
		return err
	}
	return nil
}
